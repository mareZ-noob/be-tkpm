from flask import Blueprint

from app.controllers.video_controller import (
    check_video_concat_status,
    check_video_status,
    create_video,
    delete_video,
    duplicate_video,
    generate_video_with_ffmpeg,
    generate_videos_effect_from_image,
    get_user_videos,
    update_video,
)

video_bp = Blueprint('video', __name__, url_prefix='/videos')

video_bp.route('/', methods=['POST'])(create_video)
video_bp.route('/', methods=['GET'])(get_user_videos)
video_bp.route('/<int:video_id>', methods=['PUT'])(update_video)
video_bp.route('/<int:video_id>', methods=['DELETE'])(delete_video)
video_bp.route('/<int:video_id>/duplicate', methods=['POST'])(duplicate_video)
video_bp.route('/generate', methods=['POST'])(generate_videos_effect_from_image)
video_bp.route('/status/<task_id>', methods=['GET'])(check_video_status)
video_bp.route('/generate-with-ffmpeg', methods=['POST'])(generate_video_with_ffmpeg)
video_bp.route('/concat/status/<task_id>', methods=['GET'])(check_video_concat_status)
