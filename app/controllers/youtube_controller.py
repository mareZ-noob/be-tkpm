import os
import re
import tempfile
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from celery.result import AsyncResult
from flask import jsonify, redirect, request, session, url_for
from flask_jwt_extended import jwt_required

from app.config.extensions import celery, db
from app.config.logging_config import setup_logging
from app.models import YoutubeUpload
from app.tasks.youtube_tasks import upload_from_file_task, upload_from_url_task
from app.utils.constant import API_SERVICE_NAME, API_VERSION, CLIENT_SECRETS_FILE, FRONTEND_URL, SCOPES
from app.utils.exceptions import (
    ForbiddenException,
    InternalServerException,
    InvalidCredentialsException,
    MissingParameterException,
)
from app.utils.jwt_helpers import get_user_id_from_jwt

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


@jwt_required()
def upload_video():
    logger.info("Received request to upload video.")

    user_id = get_user_id_from_jwt()
    if user_id is None:
        logger.error("Upload video request failed: User ID not found in JWT.")
        raise ForbiddenException("User ID not found in token")

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
                args=[user_id, credentials_dict, video_url, metadata]
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
                                         f"upload_{uuid4().hex}{os.path.splitext(video_file.filename)[1]}")
            video_file.save(temp_filename)
            temp_file_to_delete = temp_filename

            task = upload_from_file_task.apply_async(
                args=[user_id, credentials_dict, temp_filename, metadata]
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


@jwt_required()
def check_upload_status(task_id):
    logger.debug(f"Checking status for upload task ID: {task_id}")
    task_result = AsyncResult(task_id, app=celery)

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
            response['info'] = str(info)
        logger.error(f"Task {task_id} has unexpected state: {state}. Info: {info}")

    return jsonify(response)


def extract_video_id_from_url(url):
    if not url:
        return None
    try:
        # Standard YouTube URLs (youtube.com/watch?v=..., youtube.com/embed/..., youtu.be/...)
        parsed_url = urlparse(url)
        if "youtube.com" in parsed_url.netloc:
            if parsed_url.path == "/watch":
                video_id = parse_qs(parsed_url.query).get("v")
                if video_id:
                    return video_id[0]
            elif parsed_url.path.startswith("/embed/"):
                return parsed_url.path.split("/embed/")[1].split("?")[0]  # Get ID part
        elif "youtu.be" in parsed_url.netloc:
            return parsed_url.path[1:].split("?")[0]  # Path is /ID

        # Handle your specific format: https://www.youtube.com/watch?v={video_id}
        if "googleusercontent.com" in parsed_url.netloc and parsed_url.path.startswith("/youtube.com/"):
            # Attempt to extract the part after the last '/' assuming it's the ID
            potential_id = parsed_url.path.split('/')[-1]
            # A simple check might be len == 11 and alphanumeric/hyphen/underscore
            if potential_id and re.match(r"^[a-zA-Z0-9_-]{11}$", potential_id):
                # If it starts with '0' as per your upload tasks, maybe strip it?
                # This depends on whether the '0' is part of the ID or just prefix.
                # Assuming '0' is a prefix you added and not part of the real ID:
                if potential_id.startswith('0') and len(potential_id) > 1:
                    potential_id = potential_id[1:]
                # Re-validate length if you stripped '0'
                if re.match(r"^[a-zA-Z0-9_-]{11}$", potential_id):
                    return potential_id
                else:
                    logger.warning(
                        f"Potential ID '{potential_id}' from {url} has incorrect format after stripping '0'.")
                    return None
            elif potential_id:
                logger.warning(f"Potential ID '{potential_id}' from {url} has incorrect format.")
                return None
            else:
                return None

        logger.warning(f"Could not extract valid YouTube video ID from URL: {url}")
        return None
    except Exception as e:
        logger.error(f"Error parsing URL {url}: {e}", exc_info=True)
        return None


@jwt_required()
def get_video_stats():
    logger.info("Attempting to fetch video statistics for user's DB entries.")

    user_id = get_user_id_from_jwt()
    if user_id is None:
        logger.error("Upload video request failed: User ID not found in JWT.")
        raise ForbiddenException("User ID not found in token")

    youtube = _get_youtube_client_from_session()
    if not youtube:
        if 'credentials' not in session:
            logger.error(f"YouTube API request failed for user {user_id}: No credentials in session.")
            raise ForbiddenException("Not authenticated")
        else:
            # Credentials might be present but invalid/expired and failed refresh
            logger.error(
                f"YouTube API request failed for user {user_id}: Could not build client from session credentials.")
            # Optionally clear potentially bad credentials
            # del session['credentials']
            raise InvalidCredentialsException('Invalid or expired credentials provided')

    video_ids_from_db = []
    try:
        user_uploads = db.session.query(YoutubeUpload.url).filter(YoutubeUpload.user_id == user_id).all()
        # Explicitly close session or rely on Flask-SQLAlchemy's request context management
        # db.session.remove() # Or db.session.close() if needed outside request scope

        if not user_uploads:
            logger.info(f"No video uploads found in DB for user {user_id}.")
            return jsonify({'success': True, 'videos': []})

        for upload in user_uploads:
            video_id = extract_video_id_from_url(upload.url)
            if video_id:
                video_ids_from_db.append(video_id)
            else:
                logger.warning(f"Could not extract video ID from DB entry URL: {upload.url} for user {user_id}")

        if not video_ids_from_db:
            logger.info(f"No valid video IDs extracted from DB entries for user {user_id}.")
            return jsonify({'success': True, 'videos': []})

        logger.info(f"Found {len(video_ids_from_db)} video IDs in DB for user {user_id}.")

    except Exception as e:
        logger.error(f"Unexpected error retrieving/parsing DB videos for user {user_id}: {e}", exc_info=True)
        raise InternalServerException("An unexpected error occurred while processing video list.")

    videos_data = []
    chunk_size = 50

    try:
        for i in range(0, len(video_ids_from_db), chunk_size):
            chunk_of_ids = video_ids_from_db[i:i + chunk_size]
            ids_string = ','.join(chunk_of_ids)
            logger.debug(f"Fetching stats for video ID chunk ({i // chunk_size + 1}): {ids_string}")

            video_details_response = youtube.videos().list(
                part='snippet,statistics',
                id=ids_string
            ).execute()

            for video in video_details_response.get('items', []):
                snippet = video.get('snippet', {})
                stats = video.get('statistics', {})
                thumbnails = snippet.get('thumbnails', {})
                # Choose desired thumbnail resolution (default, medium, high, standard, maxres)
                thumbnail_url = thumbnails.get('medium', {}).get('url') or \
                                thumbnails.get('default', {}).get('url')  # Fallback

                video_data = {
                    'id': video['id'],
                    'title': snippet.get('title', 'N/A'),
                    'publishedAt': snippet.get('publishedAt'),
                    'thumbnail': thumbnail_url,
                    'views': int(stats.get('viewCount', 0)),
                    'likes': int(stats.get('likeCount', 0)),
                    'comments': int(stats.get('commentCount', 0))
                    # Dislikes ('dislikeCount') are generally unavailable via API now
                }
                videos_data.append(video_data)

        logger.info(f"Successfully fetched stats for {len(videos_data)} videos for user {user_id}.")
        return jsonify({
            'success': True,
            'videos': videos_data
        })

    except googleapiclient.errors.HttpError as e:
        error_content = e.content.decode('utf-8') if hasattr(e, 'content') else str(e)
        if e.resp.status == 401:
            if 'credentials' in session:
                del session['credentials']
            logger.error(f"YouTube API authentication error for user {user_id}: {error_content}", exc_info=True)
            raise ForbiddenException("Authentication failed with YouTube. Please re-authenticate.")
        elif e.resp.status == 403:
            logger.error(f"YouTube API forbidden error for user {user_id}: {error_content}", exc_info=True)
            raise ForbiddenException(f"YouTube API access denied (check quota or API permissions): {error_content}")
        elif e.resp.status == 404:
            logger.warning(f"YouTube API not found error for user {user_id} (IDs: {ids_string}): {error_content}")
            raise InternalServerException(f"An API error occurred (Not Found): {error_content}")
        else:
            logger.error(f"YouTube API HTTP error for user {user_id} (Status: {e.resp.status}): {error_content}",
                         exc_info=True)
            raise InternalServerException(f"An API error occurred: {error_content}")

    except Exception as e:
        logger.error(f"Unexpected error fetching YouTube stats for user {user_id}: {e}", exc_info=True)
        raise InternalServerException(f'An unexpected error occurred while fetching video statistics: {str(e)}')
