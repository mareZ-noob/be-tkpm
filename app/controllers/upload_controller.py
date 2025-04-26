import uuid

import cloudinary
import cloudinary.uploader
from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from werkzeug.utils import secure_filename

from app.config.logging_config import setup_logging
from app.models import User
from app.tasks.upload_tasks import process_avatar_upload, process_video_upload
from app.utils.constant import ALLOWED_AUDIO_EXTENSIONS, ALLOWED_IMAGE_EXTENSIONS, ALLOWED_VIDEO_EXTENSIONS
from app.utils.exceptions import (
    BadRequestException,
    InternalServerException,
    MissingParameterException,
    ResourceNotFoundException,
)

logger = setup_logging()


def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in allowed_extensions


@jwt_required()
def upload_avatar():
    user_id = None
    try:
        logger.info("Received request to upload avatar.")

        if 'file' not in request.files:
            logger.error("Avatar upload request failed: 'file' part missing in request.")
            raise MissingParameterException("Missing required fields: file")

        file = request.files['file']
        if file.filename == '':
            logger.error("Avatar upload request failed: No file selected.")
            raise MissingParameterException("Missing required fields: file")

        original_filename = file.filename
        logger.debug(f"Received avatar file: '{original_filename}'")

        if not allowed_file(original_filename, ALLOWED_IMAGE_EXTENSIONS):
            logger.error(f"Avatar upload request failed: File type not allowed for filename '{original_filename}'.")
            raise BadRequestException(f"File type not allowed for filename '{original_filename}'.")

        user_id = get_jwt_identity()
        if not user_id:
            logger.error("Avatar upload request failed: JWT identity missing or invalid.")
            raise MissingParameterException("User not found or invalid token")

        logger.info(f"Processing avatar upload request for user_id: {user_id}")

        user = User.query.get(user_id)
        if not user:
            logger.error(f"Avatar upload request failed: User with id {user_id} not found in database.")
            raise ResourceNotFoundException(f"User with id {user_id} not found in database.")

        filename = secure_filename(original_filename)
        file_data = file.read()

        logger.info(f"Dispatching avatar upload task for user_id: {user.id}, secured filename: {filename}.")
        task = process_avatar_upload.delay(user.id, file_data)
        logger.info(f"Successfully dispatched avatar upload task for user_id: {user.id}. Task ID: {task.id}")

        return jsonify({
            'msg': 'Avatar upload started',
            'task_id': task.id
        }), 202

    except Exception as e:
        logger.error(
            f"An unexpected error occurred during avatar upload request for user_id {user_id if user_id else 'unknown'}: {e}",
            exc_info=True)
        raise InternalServerException("Internal server error")


@jwt_required()
def upload_video():
    user_id = None
    try:
        logger.info("Received request to upload video.")

        if 'file' not in request.files:
            logger.error("Video upload request failed: 'file' part missing in request.")
            raise MissingParameterException("Missing required fields: file")

        file = request.files['file']
        if file.filename == '':
            logger.error("Video upload request failed: No file selected.")
            raise MissingParameterException("Missing required fields: file")

        original_filename = file.filename
        logger.debug(f"Received video file: '{original_filename}'")

        if not allowed_file(original_filename, ALLOWED_VIDEO_EXTENSIONS):
            logger.error(f"Video upload request failed: File type not allowed for filename '{original_filename}'.")
            raise BadRequestException(f"File type not allowed for filename '{original_filename}'.")

        title = request.form.get('title')  # Optional title from form data
        logger.debug(f"Received video title (optional): '{title}'")

        user_id = get_jwt_identity()
        if not user_id:
            logger.error("Video upload request failed: JWT identity missing or invalid.")
            raise MissingParameterException("User not found or invalid token")

        logger.info(f"Processing video upload request for user_id: {user_id}")

        user = User.query.get(user_id)
        if not user:
            logger.error(f"Video upload request failed: User with id {user_id} not found in database.")
            raise ResourceNotFoundException(f"User with id {user_id} not found in database.")

        filename = secure_filename(original_filename)
        file_data = file.read()

        logger.info(f"Dispatching video upload task for user_id: {user.id}, filename: {filename}, title: {title}.")
        task = process_video_upload.delay(user.id, file_data, filename, title)
        logger.info(f"Successfully dispatched video upload task for user_id: {user.id}. Task ID: {task.id}")

        return jsonify({
            'msg': 'Video upload started',
            'task_id': task.id
        }), 202

    except Exception as e:
        logger.error(
            f"An unexpected error occurred during video upload request for user_id {user_id if user_id else 'unknown'}: {e}",
            exc_info=True)
        raise InternalServerException("Internal server error")


@jwt_required()
def upload_paragraph_audio():
    user_id = None
    try:
        user_id = get_jwt_identity()
        if not user_id:
            logger.error("Paragraph audio upload failed: JWT identity missing.")
            raise MissingParameterException("User not found or invalid token")

        logger.info(f"Received request to upload paragraph audio for user_id: {user_id}.")

        if 'file' not in request.files:
            logger.error("Paragraph audio upload failed: 'file' part missing.")
            raise MissingParameterException("Missing required fields: file")

        file = request.files['file']
        if file.filename == '':
            logger.error("Paragraph audio upload failed: No file selected.")
            raise MissingParameterException("Missing required fields: file")

        original_filename = secure_filename(file.filename)  # Sanitize filename
        logger.debug(f"Received paragraph audio file: '{original_filename}' for user {user_id}")

        if not allowed_file(original_filename, ALLOWED_AUDIO_EXTENSIONS):
            logger.error(f"Paragraph audio upload failed: File type not allowed for '{original_filename}'.")
            raise BadRequestException(f"File type not allowed for filename '{original_filename}'.")

        unique_id = str(uuid.uuid4())
        public_id = f"paragraph_audio_previews/{user_id}/{unique_id}"

        logger.info(
            f"Uploading paragraph audio '{original_filename}' for user {user_id} to Cloudinary (public_id: {public_id}, resource_type: video).")

        upload_result = cloudinary.uploader.upload(
            file.stream,
            resource_type="video",
            public_id=public_id,
            overwrite=True,
            chunk_size=6000000
        )
        secure_url = upload_result.get('secure_url')

        if not secure_url:
            logger.error(
                f"Cloudinary upload failed for paragraph audio '{original_filename}', user {user_id}. No secure_url returned.")
            raise InternalServerException("Cloudinary upload failed")

        logger.info(
            f"Successfully uploaded paragraph audio '{original_filename}' for user {user_id}. URL: {secure_url}")

        return jsonify({'url': secure_url}), 200

    except cloudinary.exceptions.Error as e:
        logger.error(
            f"Cloudinary API error during paragraph audio upload for user {user_id if user_id else 'unknown'}: {e}",
            exc_info=True)
        raise InternalServerException("Unexpected error during upload")
    except Exception as e:
        logger.error(
            f"Unexpected error during paragraph audio upload for user {user_id if user_id else 'unknown'}: {e}",
            exc_info=True)
        raise InternalServerException("Unexpected error during upload")
