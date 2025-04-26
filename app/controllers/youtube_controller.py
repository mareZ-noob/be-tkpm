import os
import tempfile
import uuid

import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from celery.result import AsyncResult
from flask import jsonify, redirect, request, session, url_for

from app.config.celery_config import make_celery
from app.config.logging_config import setup_logging
from app.tasks.youtube_tasks import upload_from_file_task, upload_from_url_task
from app.utils.constant import API_SERVICE_NAME, API_VERSION, CLIENT_SECRETS_FILE, FRONTEND_URL, SCOPES
from app.utils.exceptions import (
    ForbiddenException,
    InternalServerException,
    InvalidCredentialsException,
    MissingParameterException,
    ResourceNotFoundException,
)

logger = setup_logging()


def _get_credentials_from_session():
    if 'credentials' not in session:
        logger.info('No credentials found in session')
        return None
    try:
        logger.debug('Retrieving OAuth 2.0 credentials from session')
        return google.oauth2.credentials.Credentials(**session['credentials'])
    except Exception as e:
        logger.error(f"Error loading credentials from session: {e}", exc_info=True)
        del session['credentials']
        return None


def _store_credentials_in_session(credentials):
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    session.permanent = True
    logger.info("Stored credentials in session.")


def _get_youtube_client_from_session():
    credentials = _get_credentials_from_session()
    if not credentials:
        logger.error("Cannot build YouTube client: No credentials available.")
        return None
    try:
        if credentials.expired and credentials.refresh_token:
            logger.info("Credentials expired, relying on auto-refresh.")
            credentials.refresh(google.auth.transport.requests.Request())
            _store_credentials_in_session(credentials)

        return googleapiclient.discovery.build(
            API_SERVICE_NAME, API_VERSION, credentials=credentials
        )
    except Exception as e:
        logger.error(f"Failed to build YouTube client: {e}", exc_info=True)
        return None


def authorize_youtube():
    try:
        logger.info("Initiating YouTube authorization flow.")
        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE, scopes=SCOPES)
        # callback_url = url_for('youtube.oauth2_callback', _external=True, _scheme='https')
        # flow.redirect_uri = callback_url
        flow.redirect_uri = request.base_url + '/callback'
        logger.info(f"Using redirect URI: {flow.redirect_uri}")
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        session['state'] = state
        logger.info(f"Generated authorization URL. State stored in session: {state}")
        return jsonify({'auth_url': authorization_url})
    except Exception as e:
        logger.error(f"Failed to generate authorization URL: {e}", exc_info=True)
        return None


def oauth2_callback():
    logger.info("Received OAuth2 callback.")
    # state = session.pop('state', None)
    state = session.get('state', '')
    # if not state or state != request.args.get('state'):
    #     logger.error("OAuth state mismatch.")
    #     return jsonify({'error': 'Invalid state parameter'}), 400

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, state=state)
    # flow.redirect_uri = url_for('youtube.oauth2_callback', _external=True)
    flow.redirect_uri = request.base_url

    authorization_response = request.url
    if not request.is_secure:
        # If your app isn't served over HTTPS but Google requires it for callbacks,
        # you might need to manually reconstruct the URL with https
        # This depends heavily on your deployment setup (proxy headers etc.)
        # Example (may need adjustment):
        # authorization_response = authorization_response.replace("http://", "https://", 1)
        pass

    try:
        flow.fetch_token(authorization_response=authorization_response)
        credentials = flow.credentials
        logger.info("OAuth token fetched successfully.")
        _store_credentials_in_session(credentials)
        return redirect(f'{FRONTEND_URL}/dashboard')
    except Exception as e:
        logger.error(f"Error fetching OAuth token: {e}")
        raise InvalidCredentialsException('Invalid credentials provided')


def get_auth_status():
    logger.debug("Checking authentication status.")
    credentials = _get_credentials_from_session()
    is_authenticated = bool(credentials and (credentials.token or credentials.refresh_token))
    logger.info(f"User authentication status: {is_authenticated}")
    return jsonify({'is_authenticated': is_authenticated})


def logout_youtube():
    logger.info("Processing logout request.")
    if 'credentials' in session:
        # Optional: Revoke the token on Google's side
        # credentials = _get_credentials_from_session()
        # if credentials and credentials.token:
        #     try:
        #         requests.post('https://oauth2.googleapis.com/revoke',
        #             params={'token': credentials.token},
        #             headers = {'content-type': 'application/x-www-form-urlencoded'})
        #     except Exception as e:
        #         logger.error(f"Failed to revoke token: {e}")
        del session['credentials']
    return jsonify({'msg': 'Logged out successfully'})


def upload_video():
    logger.info("Received request to upload video.")
    if 'credentials' not in session:
        logger.error("Upload video request failed: No credentials found in session.")
        raise ForbiddenException("Not authenticated")

    credentials_dict = session['credentials']

    metadata = {
        'title': 'Untitled Video',
        'description': '',
        'tags': [],
        'privacyStatus': 'private',
        'categoryId': '28'
    }

    task = None
    temp_file_to_delete = None

    try:
        if request.is_json:
            data = request.get_json()
            video_url = data.get('video_url')
            if not video_url:
                logger.error("Upload video request failed: No video URL provided")
                raise MissingParameterException("Missing video URL")

            metadata.update({
                'title': data.get('title', metadata['title']),
                'description': data.get('description', metadata['description']),
                'tags': data.get('tags', metadata['tags']),
                'privacyStatus': data.get('privacy_status', metadata['privacyStatus'])
            })

            task = upload_from_url_task.apply_async(
                args=[credentials_dict, video_url, metadata]
            )

        else:
            if 'file' not in request.files:
                logger.error("Upload video request failed: No file provided")
                raise MissingParameterException("Missing video file")

            video_file = request.files['file']
            if not video_file or not video_file.filename:
                logger.error("Upload video request failed: No file selected")
                raise MissingParameterException("Missing file")

            metadata.update({
                'title': request.form.get('title', metadata['title']),
                'description': request.form.get('description', metadata['description']),
                'tags': request.form.get('tags', '').split(',') if request.form.get('tags') else [],
                'privacyStatus': request.form.get('privacy_status', metadata['privacyStatus'])
            })

            temp_dir = tempfile.gettempdir()
            temp_filename = os.path.join(temp_dir,
                                         f"upload_{uuid.uuid4().hex}{os.path.splitext(video_file.filename)[1]}")
            video_file.save(temp_filename)
            temp_file_to_delete = temp_filename

            task = upload_from_file_task.apply_async(
                args=[credentials_dict, temp_filename, metadata]
            )
            temp_file_to_delete = None

    except Exception as e:
        logger.error(f"Error initiating upload task: {e}", exc_info=True)
        if temp_file_to_delete and os.path.exists(temp_file_to_delete):
            try:
                os.remove(temp_file_to_delete)
            except OSError as rm_err:
                logger.error(f"Error removing temp file during exception: {rm_err}", exc_info=True)
        raise InternalServerException(f'Failed to start upload task: {str(e)}')

    if task:
        status_url = url_for('youtube.check_upload_status', task_id=task.id, _external=True)
        return jsonify({
            'success': True,
            'task_id': task.id,
            'status': 'Video upload started in background',
            'status_url': status_url
        })
    else:
        logger.error("Error initiating upload task")
        raise InternalServerException("Failed to start upload task")


def check_upload_status(task_id):
    logger.debug(f"Checking status for upload task ID: {task_id}")
    celery_app = make_celery()
    task_result = AsyncResult(task_id, app=celery_app)

    state = task_result.state
    # Info dictionary provided by task update_state
    info = task_result.info

    response = {'state': state}
    logger.debug(f"Checking status for upload task ID: {task_id}")

    if state == 'PENDING':
        logger.info(f"Task {task_id} is PENDING.")
        response['status'] = 'Upload pending or task ID unknown.'
    elif state == 'FAILURE':
        response['status'] = 'Upload failed.'
        error_info = info if isinstance(info, str) else str(info.get('error', info))
        response['error'] = error_info
        logger.error(f"Task {task_id} FAILED. Error: {error_info}")
    elif state in ['DOWNLOADING', 'UPLOADING', 'PROGRESS']:  # Use 'PROGRESS' as a generic state
        response['status'] = info.get('status', 'Processing...')
        response['current'] = info.get('current', 0)
        response['total'] = info.get('total', 100)
        # Calculate percentage
        total = response['total']
        current = response['current']
        response['percent'] = int(current / total * 100) if total > 0 else 0
        logger.info(f"Task {task_id} is in progress: {response['status']} ({response['percent']}%)")
    elif state == 'SUCCESS':
        response['status'] = 'Upload completed successfully.'
        response['result'] = task_result.result
        logger.info(f"Task {task_id} SUCCEEDED. Result: {response['result']}")
    else:
        response['status'] = 'Unknown task state.'
        if info:
            response['info'] = str(info)  # Include any info for debugging
        logger.error(f"Task {task_id} has unexpected state: {state}. Info: {info}")

    return jsonify(response)


def get_video_stats():
    logger.info("Attempting to fetch video statistics.")
    youtube = _get_youtube_client_from_session()
    if not youtube:
        if 'credentials' not in session:
            logger.error("YouTube API request failed: No credentials found in session.")
            raise ForbiddenException("Not authenticated")
        else:
            logger.error("YouTube API request failed: No credentials found in session.")
            raise InvalidCredentialsException('Invalid credentials provided')
    try:
        # Get channel ID (using 'mine=True')
        channels_response = youtube.channels().list(
            part='contentDetails',
            mine=True
        ).execute()

        if not channels_response.get('items'):
            logger.error("Google API error: Could not find YouTube channel for this account")
            raise ResourceNotFoundException('Could not find YouTube channel for this account')

        # Get the ID of the uploads playlist
        uploads_playlist_id = channels_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

        # Paginate through the uploads playlist to get video IDs
        videos_data = []
        next_page_token = None
        while True:
            playlist_items_response = youtube.playlistItems().list(
                part='contentDetails',  # Only need videoId here
                playlistId=uploads_playlist_id,
                maxResults=50,  # Max allowed by API
                pageToken=next_page_token
            ).execute()

            video_ids = [
                item['contentDetails']['videoId']
                for item in playlist_items_response.get('items', [])
                if item.get('contentDetails', {}).get('videoId')  # Ensure videoId exists
            ]

            if not video_ids:
                break

            # Get details and statistics for the collected video IDs in batches
            video_details_response = youtube.videos().list(
                part='snippet,statistics',  # Get title, thumbs, pubdate, and stats
                id=','.join(video_ids)
            ).execute()

            for video in video_details_response.get('items', []):
                snippet = video.get('snippet', {})
                stats = video.get('statistics', {})
                thumbnails = snippet.get('thumbnails', {})
                default_thumbnail = thumbnails.get('default', {})  # Or 'medium', 'high'

                video_data = {
                    'id': video['id'],
                    'title': snippet.get('title', 'N/A'),
                    'publishedAt': snippet.get('publishedAt'),
                    'thumbnail': default_thumbnail.get('url'),
                    'views': int(stats.get('viewCount', 0)),
                    'likes': int(stats.get('likeCount', 0)),
                    # 'dislikes' are often hidden/unavailable now
                    # 'dislikes': int(stats.get('dislikeCount', 0)),
                    'comments': int(stats.get('commentCount', 0))
                }
                videos_data.append(video_data)

            # Check for the next page of playlist items
            next_page_token = playlist_items_response.get('nextPageToken')
            if not next_page_token:
                break

        return jsonify({
            'success': True,
            'videos': videos_data
        })

    except googleapiclient.errors.HttpError as e:
        error_content = e.content.decode('utf-8') if hasattr(e, 'content') else str(e)
        if e.resp.status == 401:
            if 'credentials' in session: del session['credentials']
            logger.error(f"YouTube API error: {error_content}")
            raise ForbiddenException("Not authenticated")
        logger.error(f"YouTube API error: {error_content}")
        return jsonify({'error': f"An API error occurred: {error_content}"}), e.resp.status
    except Exception as e:
        logger.error(f"Unexpected error fetching video stats: {e}", exc_info=True)
        raise InternalServerException(f'An unexpected error occurred: {str(e)}')
