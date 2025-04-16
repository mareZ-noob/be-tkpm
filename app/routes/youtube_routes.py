from flask import Blueprint

from app.controllers.youtube_controller import (
    authorize_youtube,
    check_upload_status,
    get_auth_status,
    get_video_stats,
    logout_youtube,
    oauth2_callback,
    upload_video,
)

youtube_bp = Blueprint('youtube', __name__, url_prefix='/youtube')

# Authorization routes
youtube_bp.route('/auth', methods=['GET'])(authorize_youtube)
youtube_bp.route('/auth/callback', methods=['GET'])(oauth2_callback)
youtube_bp.route('/auth/status', methods=['GET'])(get_auth_status)
youtube_bp.route('/auth/logout', methods=['GET'])(logout_youtube)

# Video operations
youtube_bp.route('/videos/upload', methods=['POST'])(upload_video)
youtube_bp.route('/videos/upload/status/<task_id>', methods=['GET'])(check_upload_status)
youtube_bp.route('/videos/stats', methods=['GET'])(get_video_stats)