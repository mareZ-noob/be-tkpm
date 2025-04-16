import os
import tempfile
import uuid

import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from celery.result import AsyncResult
from flask import current_app, jsonify, redirect, request, session, url_for

from app.config.celery_config import make_celery
from app.tasks.youtube_tasks import upload_from_file_task, upload_from_url_task
from app.utils.constant import API_SERVICE_NAME, API_VERSION, CLIENT_SECRETS_FILE, FRONTEND_URL, SCOPES


def _get_credentials_from_session():
    if 'credentials' not in session:
        return None
    try:
        return google.oauth2.credentials.Credentials(**session['credentials'])
    except Exception as e:
        current_app.logger.error(f"Error loading credentials from session: {e}")
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


def _get_youtube_client_from_session():
    credentials = _get_credentials_from_session()
    if not credentials:
        return None
    try:
        if credentials.expired and credentials.refresh_token:
            current_app.logger.info("Credentials expired, relying on auto-refresh.")
            credentials.refresh(google.auth.transport.requests.Request())
            _store_credentials_in_session(credentials)

        return googleapiclient.discovery.build(
            API_SERVICE_NAME, API_VERSION, credentials=credentials
        )
    except Exception as e:
        current_app.logger.error(f"Failed to build YouTube client: {e}")
        return None


def authorize_youtube():
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES)
    # callback_url = url_for('youtube.oauth2_callback', _external=True)
    # flow.redirect_uri = callback_url
    flow.redirect_uri = request.base_url + '/callback'

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    session['state'] = state
    return jsonify({'auth_url': authorization_url})


def oauth2_callback():
    # state = session.pop('state', None)
    state = session.get('state', '')
    # if not state or state != request.args.get('state'):
    #     current_app.logger.warning("OAuth state mismatch.")
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
        _store_credentials_in_session(credentials)
        return redirect(f'{FRONTEND_URL}/dashboard')
    except Exception as e:
        current_app.logger.error(f"Error fetching OAuth token: {e}")
        return jsonify({'error': f'Failed to fetch token: {str(e)}'}), 400


def get_auth_status():
    credentials = _get_credentials_from_session()
    is_authenticated = bool(credentials and (credentials.token or credentials.refresh_token))
    return jsonify({'is_authenticated': is_authenticated})


def logout_youtube():
    if 'credentials' in session:
        # Optional: Revoke the token on Google's side
        # credentials = _get_credentials_from_session()
        # if credentials and credentials.token:
        #     try:
        #         requests.post('https://oauth2.googleapis.com/revoke',
        #             params={'token': credentials.token},
        #             headers = {'content-type': 'application/x-www-form-urlencoded'})
        #     except Exception as e:
        #         current_app.logger.warning(f"Failed to revoke token: {e}")
        del session['credentials']
    return jsonify({'msg': 'Logged out successfully'})


def upload_video():
    if 'credentials' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

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
                return jsonify({'error': 'No video URL provided'}), 400

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
                return jsonify({'error': 'No file provided'}), 400

            video_file = request.files['file']
            if not video_file or not video_file.filename:
                return jsonify({'error': 'Invalid file provided'}), 400

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
        current_app.logger.error(f"Error initiating upload task: {e}")
        if temp_file_to_delete and os.path.exists(temp_file_to_delete):
            try:
                os.remove(temp_file_to_delete)
            except OSError as rm_err:
                current_app.logger.error(f"Error removing temp file during exception: {rm_err}")
        return jsonify({'error': f'Failed to start upload task: {str(e)}'}), 500

    if task:
        status_url = url_for('youtube.check_upload_status', task_id=task.id, _external=True)
        return jsonify({
            'success': True,
            'task_id': task.id,
            'status': 'Video upload started in background',
            'status_url': status_url
        })
    else:
        return jsonify({'error': 'Upload task could not be created'}), 500


def check_upload_status(task_id):
    celery_app = make_celery()
    task_result = AsyncResult(task_id, app=celery_app)

    state = task_result.state
    # Info dictionary provided by task update_state
    info = task_result.info

    response = {'state': state}

    if state == 'PENDING':
        response['status'] = 'Upload pending or task ID unknown.'
    elif state == 'FAILURE':
        response['status'] = 'Upload failed.'
        error_info = info if isinstance(info, str) else str(info.get('error', info))
        response['error'] = error_info
    elif state in ['DOWNLOADING', 'UPLOADING', 'PROGRESS']:  # Use 'PROGRESS' as a generic state
        response['status'] = info.get('status', 'Processing...')
        response['current'] = info.get('current', 0)
        response['total'] = info.get('total', 100)
        # Calculate percentage
        total = response['total']
        current = response['current']
        response['percent'] = int(current / total * 100) if total > 0 else 0
    elif state == 'SUCCESS':
        response['status'] = 'Upload completed successfully.'
        response['result'] = task_result.result
    else:
        response['status'] = 'Unknown task state.'
        if info:
            response['info'] = str(info)  # Include any info for debugging

    return jsonify(response)


def get_video_stats():
    youtube = _get_youtube_client_from_session()
    if not youtube:
        if 'credentials' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        else:
            return jsonify({'error': 'Failed to create YouTube client, possibly invalid credentials'}), 500

    try:
        # Get channel ID (using 'mine=True')
        channels_response = youtube.channels().list(
            part='contentDetails',
            mine=True
        ).execute()

        if not channels_response.get('items'):
            return jsonify({'error': 'Could not find YouTube channel for this account'}), 404

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
            return jsonify({'error': f'Authentication error: {error_content}', 'auth_required': True}), 401
        current_app.logger.error(f"YouTube API error: {error_content}")
        return jsonify({'error': f"An API error occurred: {error_content}"}), e.resp.status
    except Exception as e:
        current_app.logger.error(f"Unexpected error fetching video stats: {e}")
        return jsonify({'error': f'An unexpected error occurred: {str(e)}'}), 500
