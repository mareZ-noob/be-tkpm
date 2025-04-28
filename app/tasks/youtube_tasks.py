import os
import tempfile
import time

import google.oauth2.credentials
import googleapiclient.discovery
import googleapiclient.errors
import googleapiclient.http
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from app.config.extensions import celery, db
from app.config.logging_config import setup_logging
from app.models import YoutubeUpload
from app.utils.constant import (
    API_SERVICE_NAME,
    API_VERSION,
    CHUNK_SIZE,
    DOWNLOAD_BACKOFF_FACTOR,
    DOWNLOAD_RETRIES,
    DOWNLOAD_TIMEOUT,
)

logger = setup_logging()


def _build_youtube_client_from_dict(credentials_dict):
    try:
        credentials = google.oauth2.credentials.Credentials(
            token=credentials_dict.get('token'),
            refresh_token=credentials_dict.get('refresh_token'),
            token_uri=credentials_dict.get('token_uri'),
            client_id=credentials_dict.get('client_id'),
            client_secret=credentials_dict.get('client_secret'),
            scopes=credentials_dict.get('scopes')
        )
        return googleapiclient.discovery.build(
            API_SERVICE_NAME, API_VERSION, credentials=credentials
        )
    except Exception as e:
        logger.error(f"Error building YouTube client in task: {e}", exc_info=True)
        raise


def _perform_youtube_upload(task_instance, youtube, file_path, metadata):
    body = {
        'snippet': {
            'title': metadata.get('title', 'Untitled'),
            'description': metadata.get('description', ''),
            'tags': metadata.get('tags', []),
            'categoryId': metadata.get('categoryId', '28')
        },
        'status': {
            'privacyStatus': metadata.get('privacyStatus', 'private')
        }
    }

    f = None
    try:
        logger.info(f"Attempting to open file for upload: {file_path}")
        f = open(file_path, 'rb')
        logger.info(f"File opened successfully: {file_path}")

        media_body = googleapiclient.http.MediaIoBaseUpload(
            f,
            mimetype='video/*',
            chunksize=CHUNK_SIZE,
            resumable=True
        )

        upload_request = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media_body
        )

        response = None
        last_progress_update_time = time.time()
        logger.info("Starting upload loop...")
        while response is None:
            try:
                status, response = upload_request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    now = time.time()
                    if progress == 100 or (now - last_progress_update_time > 2):
                        task_instance.update_state(
                            state='UPLOADING',
                            meta={
                                'current': progress,
                                'total': 100,
                                'status': f'Uploading to YouTube: {progress}%'
                            }
                        )
                        last_progress_update_time = now
                        print(f"Upload progress: {progress}%")
            except googleapiclient.errors.HttpError as e:
                logger.error(f"API Error during upload chunk: {e}", exc_info=True)
                raise

        logger.info(f"Upload loop finished. Finalizing. Response: {response}")
        logger.info(f"Upload successful. Video ID: {response.get('id')}")
        return response

    except FileNotFoundError as e:
        logger.error(f"File not found error: {e}", exc_info=True)
        task_instance.update_state(state='FAILURE', meta={'error': str(e)})
        raise
    finally:
        if f and not f.closed:
            try:
                f.close()
                logger.info(f"Closed file handle for {file_path}")
            except Exception as close_err:
                logger.error(f"Error closing file handle for {file_path}: {close_err}", exc_info=True)
        elif f and f.closed:
            logger.info(f"File handle for {file_path} was already closed.")
        else:
            logger.info(f"No file handle to close for {file_path} (or it was never opened).")


def download_video_from_url(video_url, task_instance=None):
    temp_file_path = None
    try:
        temp_dir = tempfile.gettempdir()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4", dir=temp_dir) as temp_file:
            temp_file_path = temp_file.name

            session = requests.Session()
            retries = Retry(total=DOWNLOAD_RETRIES,
                            backoff_factor=DOWNLOAD_BACKOFF_FACTOR,
                            status_forcelist=[500, 502, 503, 504])  # Retry on server errors
            session.mount('http://', HTTPAdapter(max_retries=retries))
            # session.mount('https://', HTTPAdapter(max_retries=retries))

            response = session.get(video_url, stream=True, timeout=DOWNLOAD_TIMEOUT)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            last_progress_update_time = time.time()

            if task_instance:
                task_instance.update_state(state='DOWNLOADING', meta={
                    'current': 0, 'total': 100, 'status': 'Starting download...', 'bytes_total': total_size
                })

            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
                    downloaded_size += len(chunk)
                    now = time.time()
                    if task_instance and total_size > 0 and (now - last_progress_update_time > 1):
                        percent = int(downloaded_size / total_size * 100)
                        task_instance.update_state(state='DOWNLOADING', meta={
                            'current': percent, 'total': 100,
                            'status': f'Downloading: {percent}% ({downloaded_size}/{total_size} bytes)',
                            'bytes_downloaded': downloaded_size, 'bytes_total': total_size
                        })
                        last_progress_update_time = now

        logger.info(f"Video downloaded successfully to: {temp_file_path}")
        if task_instance:
            task_instance.update_state(state='DOWNLOADING', meta={
                'current': 100, 'total': 100,
                'status': f'Download complete ({downloaded_size} bytes)',
                'bytes_downloaded': downloaded_size, 'bytes_total': total_size
            })
        return temp_file_path

    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading video from URL {video_url}: {e}", exc_info=True)
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError as rm_err:
                logger.error(f"Error removing partial download {temp_file_path}: {rm_err}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during video download: {e}", exc_info=True)
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError as rm_err:
                logger.error(f"Error removing partial download {temp_file_path} during unexpected error: {rm_err}",
                             exc_info=True)
        return None


@celery.task(bind=True, max_retries=3, default_retry_delay=60,
             soft_time_limit=7200, time_limit=7200)
def upload_from_url_task(self, user_id, credentials_dict, video_url, metadata):
    temp_file_path = None
    try:
        temp_file_path = download_video_from_url(video_url, self)
        if not temp_file_path:
            self.update_state(state='FAILURE', meta={'error': 'Failed to download video from URL'})
            return {'success': False, 'error': 'Failed to download video from URL'}

        logger.info(f"Task {self.request.id}: Video downloaded to {temp_file_path}. Building YouTube client.")
        youtube = _build_youtube_client_from_dict(credentials_dict)

        logger.info(f"Task {self.request.id}: Starting YouTube upload via _perform_youtube_upload.")
        response = _perform_youtube_upload(self, youtube, temp_file_path, metadata)

        video_id = response.get('id')
        logger.info(f"Task {self.request.id}: YouTube upload successful. Video ID: {video_id}")

        if video_id:
            try:
                yt_url = f"https://www.youtube.com/watch?v={video_id}"
                title = metadata.get('title', 'Untitled Video')  # Use the same title
                new_upload = YoutubeUpload(user_id=user_id, url=yt_url, title=title)

                db.session.add(new_upload)
                db.session.commit()
                logger.info(
                    f"Task {self.request.id}: Successfully saved upload record to DB (ID: {new_upload.id}) for video {video_id}.")
                db_id = new_upload.id

                return {
                    'success': True,
                    'video_id': video_id,
                    'db_id': db_id,
                    'msg': 'Video downloaded, uploaded, and DB record created successfully'
                }
            except Exception as e:
                db.session.rollback()
                logger.error(f"Task {self.request.id}: Unexpected error during DB save for video {video_id}: {e}",
                             exc_info=True)
                self.update_state(state='FAILURE', meta={
                    'video_id': video_id,
                    'error': f'Unexpected error during DB save: {str(e)}'
                })
                return {'success': False, 'video_id': video_id, 'error': f'Unexpected error during DB save: {str(e)}'}
        else:
            logger.warning(
                f"Task {self.request.id}: YouTube upload response did not contain a video ID. Cannot save to DB.")
            self.update_state(state='FAILURE', meta={'error': 'Upload response missing video ID'})
            return {'success': False, 'error': 'Upload response missing video ID'}
    except googleapiclient.errors.HttpError as e:
        error_message = e.content.decode('utf-8') if hasattr(e, 'content') else str(e)
        self.update_state(state='FAILURE', meta={'error': f"YouTube API error: {error_message}"})
        return {'success': False, 'error': f"YouTube API error: {error_message}"}
    except Exception as e:
        logger.error(f"Unhandled exception in upload_from_url_task: {e}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': f"An unexpected error occurred: {str(e)}"})
        return {'success': False, 'error': f"An unexpected error occurred: {str(e)}"}
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                print(f"Cleaned up temporary file: {temp_file_path}")
            except OSError as e:
                print(f"Error cleaning up temporary file {temp_file_path}: {e}")


@celery.task(bind=True, max_retries=3, default_retry_delay=60,
             soft_time_limit=7200, time_limit=7200)
def upload_from_file_task(self, user_id, credentials_dict, file_path, metadata):
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Input file path not found: {file_path}")

        logger.info(f"Task {self.request.id}: Building YouTube client.")
        youtube = _build_youtube_client_from_dict(credentials_dict)

        logger.info(f"Task {self.request.id}: Starting YouTube upload via _perform_youtube_upload.")
        response = _perform_youtube_upload(self, youtube, file_path, metadata)
        video_id = response.get('id')
        logger.info(f"Task {self.request.id}: YouTube upload successful. Video ID: {video_id}")

        if video_id:
            try:
                yt_url = f"https://www.youtube.com/watch?v={video_id}"
                title = metadata.get('title', 'Untitled Video')
                new_upload = YoutubeUpload(user_id=user_id, url=yt_url, title=title)

                db.session.add(new_upload)
                db.session.commit()
                logger.info(
                    f"Task {self.request.id}: Successfully saved upload record to DB (ID: {new_upload.id}) for video {video_id}.")
                db_id = new_upload.id

                return {
                    'success': True,
                    'video_id': video_id,
                    'db_id': db_id,
                    'msg': 'Video uploaded from file and DB record created successfully'
                }
            except Exception as e:
                db.session.rollback()
                logger.error(f"Task {self.request.id}: Unexpected error during DB save for video {video_id}: {e}",
                             exc_info=True)
                self.update_state(state='FAILURE', meta={
                    'video_id': video_id,
                    'error': f'Unexpected error during DB save: {str(e)}'
                })
                return {'success': False, 'video_id': video_id, 'error': f'Unexpected error during DB save: {str(e)}'}
        else:
            logger.warning(
                f"Task {self.request.id}: YouTube upload response did not contain a video ID. Cannot save to DB.")
            self.update_state(state='FAILURE', meta={'error': 'Upload response missing video ID'})
            return {'success': False, 'error': 'Upload response missing video ID'}

    except FileNotFoundError as e:
        logger.error(f"File not found error in upload_from_file_task: {e}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        return {'success': False, 'error': str(e)}
    except googleapiclient.errors.HttpError as e:
        error_message = e.content.decode('utf-8') if hasattr(e, 'content') else str(e)
        self.update_state(state='FAILURE', meta={'error': f"YouTube API error: {error_message}"})
        return {'success': False, 'error': f"YouTube API error: {error_message}"}
    except Exception as e:
        logger.error(f"Unhandled exception in upload_from_file_task: {e}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': f"An unexpected error occurred: {str(e)}"})
        return {'success': False, 'error': f"An unexpected error occurred: {str(e)}"}
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up provided file: {file_path}")
            except OSError as e:
                logger.error(f"Error cleaning up provided file {file_path}: {e}", exc_info=True)
