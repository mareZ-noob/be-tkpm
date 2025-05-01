from flask import Blueprint

from app.controllers.image_controller import check_image_status, generate_image

image_bp = Blueprint('image', __name__, url_prefix='/images')

image_bp.route('/generate', methods=['POST'])(generate_image)
image_bp.route('/status/<task_id>', methods=['GET'])(check_image_status)