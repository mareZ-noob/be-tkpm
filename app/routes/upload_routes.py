from flask import Blueprint

from app.controllers.upload_controller import upload_avatar, upload_video

upload_bp = Blueprint('upload', __name__, url_prefix='/upload')

upload_bp.route('/avatar', methods=['PUT'])(upload_avatar)
upload_bp.route('/video', methods=['PUT'])(upload_video)
