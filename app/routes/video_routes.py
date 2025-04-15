from flask import Blueprint

from app.controllers.video_controller import create_video, delete_video, duplicate_video, get_user_videos, update_video

video_bp = Blueprint('video', __name__, url_prefix='/videos')

video_bp.route('/', methods=['POST'])(create_video)
video_bp.route('/', methods=['GET'])(get_user_videos)
video_bp.route('/<int:video_id>', methods=['PUT'])(update_video)
video_bp.route('/<int:video_id>', methods=['DELETE'])(delete_video)
video_bp.route('/<int:video_id>/duplicate', methods=['POST'])(duplicate_video)
