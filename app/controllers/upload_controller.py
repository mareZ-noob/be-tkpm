import os

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from werkzeug.utils import secure_filename

from app.config.extensions import db
from app.models import User, Video
from app.tasks.upload_tasks import process_avatar_upload, process_video_upload
from app.utils.constant import ALLOWED_IMAGE_EXTENSIONS, ALLOWED_VIDEO_EXTENSIONS


def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in allowed_extensions


@jwt_required()
def upload_avatar():
    try:
        if 'file' not in request.files:
            return jsonify({'msg': 'No file part'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'msg': 'No selected file'}), 400

        if not allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
            return jsonify({'msg': 'File type not allowed'}), 400

        current_user = get_jwt_identity()
        if not current_user:
            return jsonify({"msg": "User not found"}), 404

        user = User.query.get(current_user)
        if not user:
            return jsonify({"msg": "User not found"}), 404

        filename = secure_filename(file.filename)

        task = process_avatar_upload.delay(user.id, file.read(), filename)

        return jsonify({
            'msg': 'Avatar upload started',
            'task_id': task.id
        }), 202

    except Exception as e:
        return jsonify({'msg': str(e)}), 500


def upload_video():
    try:
        if 'file' not in request.files:
            return jsonify({'msg': 'No file part'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'msg': 'No selected file'}), 400

        if not allowed_file(file.filename, ALLOWED_VIDEO_EXTENSIONS):
            return jsonify({'msg': 'File type not allowed'}), 400

        title = request.form.get('title')

        current_user = get_jwt_identity()
        if not current_user:
            return jsonify({"msg": "User not found"}), 404

        user = User.query.get(current_user)
        if not user:
            return jsonify({"msg": "User not found"}), 404

        filename = secure_filename(file.filename)

        task = process_video_upload.delay(user.id, file.read(), filename, title)

        return jsonify({
            'msg': 'Video upload started',
            'task_id': task.id
        }), 202

    except Exception as e:
        return jsonify({'error': str(e)}), 500
