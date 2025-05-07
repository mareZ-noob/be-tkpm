import math

from celery.result import AsyncResult
from flask import jsonify, request, url_for
from flask_jwt_extended import get_jwt_identity, jwt_required
from werkzeug.utils import secure_filename

from app.config.extensions import celery, db
from app.config.logging_config import setup_logging
from app.models import Video
from app.tasks.video_tasks import concat_video, process_image_to_video_effects
from app.utils.constant import ALLOWED_IMAGE_EXTENSIONS
from app.utils.exceptions import (
    BadRequestException,
    InternalServerException,
    MissingParameterException,
    ResourceNotFoundException,
)
from app.utils.function_helpers import allowed_file
from app.utils.jwt_helpers import get_user_from_jwt

logger = setup_logging()


@jwt_required()
def create_video():
    data = request.get_json()
    current_user = get_jwt_identity()
    url = data.get('url')
    title = data.get('title', 'Untitled')

    if not current_user or not url:
        logger.error("Create video failed: User not found.")
        raise ResourceNotFoundException("User not found")

    new_video = Video(user_id=current_user, url=url, title=title)
    db.session.add(new_video)
    db.session.commit()

    logger.info(f"New video created: {new_video}")
    return jsonify(new_video.to_dict()), 201


@jwt_required()
def update_video(video_id):
    video = Video.query.get(video_id)
    if not video:
        logger.error("Update video failed: Video not found")
        raise ResourceNotFoundException("Video not found")

    data = request.get_json()
    video.from_dict(data)
    db.session.commit()

    logger.info(f"Video updated: {video}")
    return jsonify(video.to_dict())


@jwt_required()
def delete_video(video_id):
    video = Video.query.get(video_id)
    if not video:
        logger.error("Delete video failed: Video not found")
        raise ResourceNotFoundException("Video not found")

    logger.info(f"Video deleted: {video}")
    db.session.delete(video)
    db.session.commit()

    logger.info(f"Delete video: {video_id}")
    return jsonify({"msg": "Video deleted"}), 200


@jwt_required()
def get_user_videos():
    user = get_user_from_jwt()
    if user is None:
        logger.error("Get user video failed: User not found.")
        raise ResourceNotFoundException("User not found")
    videos = Video.query.filter_by(user_id=user.id).all()
    return jsonify([video.to_dict() for video in videos])


@jwt_required()
def duplicate_video(video_id):
    video = Video.query.get(video_id)
    if not video:
        logger.error("Duplicate video failed: Video not found")
        raise ResourceNotFoundException("Video not found")

    data = request.get_json()
    title = data.get('title', 'Untitled')

    new_video = Video(
        user_id=video.user_id,
        url=video.url,
        title=title,
        starred=video.starred
    )
    db.session.add(new_video)
    db.session.commit()

    logger.info(f"Duplicate video created: {new_video}")
    return jsonify(new_video.to_dict()), 201


@jwt_required()
def generate_videos_effect_from_image():
    user = get_user_from_jwt()
    if user is None:
        logger.error("Generate video effects failed: User not found.")
        raise ResourceNotFoundException("User not found")

    if 'images' not in request.files:
        logger.error(f"Generate video effects failed for user {user.id}: No 'images' file part.")
        raise BadRequestException("No file part named 'images' in the request.")

    # Retrieve duration from form-data
    duration = request.form.get('duration')
    if not duration:
        logger.error(f"Generate video effects failed for user {user.id}: Missing duration.")
        raise MissingParameterException("Missing required field: duration")

    try:
        duration = float(duration)
        if duration <= 0:
            logger.error(
                f"Generate video effects failed for user {user.id}: Invalid duration {duration}.")
            raise BadRequestException("duration must be a positive number.")
    except ValueError:
        logger.error(
            f"Generate video effects failed for user {user.id}: Invalid duration format {duration}.")
        raise BadRequestException("duration must be a valid number.")

    duration = int(math.ceil(duration))
    files = request.files.getlist('images')
    if not files or all(f.filename == '' for f in files):
        logger.error(f"Generate video effects failed for user {user.id}: No files selected.")
        raise BadRequestException("No files selected for upload.")

    tasks = []
    processed_files = 0
    valid_files = []

    # First pass: Validate files and count valid ones
    for file in files:
        if file and file.filename and allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
            filename = secure_filename(file.filename)
            try:
                file_data = file.read()
                if not file_data:
                    logger.warning(f"Skipping empty file: {filename} for user {user.id}")
                    continue
                # Store valid file info for second pass
                valid_files.append({'file': file, 'filename': filename, 'file_data': file_data})
                processed_files += 1
            except Exception as e:
                logger.error(f"Error reading file '{filename}' for user {user.id}: {e}", exc_info=True)
                tasks.append({
                    'task_id': None,
                    'filename': filename,
                    'error': f"Error reading file: {str(e)}"
                })
                processed_files += 1
        elif file and file.filename:
            filename = secure_filename(file.filename)
            logger.warning(f"Skipping file with disallowed extension: {filename} for user {user.id}")
            tasks.append({
                'task_id': None,
                'filename': filename,
                'error': f"File type not allowed. Allowed types: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"
            })
            processed_files += 1

    if processed_files == 0:
        logger.error(f"User {user.id}: No files were processed for video effects.")
        raise BadRequestException("No files were processed for video effects.")

    # Calculate duration per part
    num_valid_files = len(valid_files)
    if num_valid_files == 0:
        logger.error(f"User {user.id}: No valid files were processed for video effects.")
        raise BadRequestException("No valid files were processed for video effects.")

    duration_per_part = duration / num_valid_files
    logger.info(
        f"Received {num_valid_files} valid image(s) for video effects processing from user {user.id} "
        f"with duration {duration}s, duration_per_part {duration_per_part:.2f}s."
    )

    # Second pass: Submit tasks for valid files
    for valid_file in valid_files:
        filename = valid_file['filename']
        file_data = valid_file['file_data']
        try:
            # Submit task to Celery with duration_per_part
            task = process_image_to_video_effects.apply_async(
                args=[user.id, file_data, filename, duration_per_part]
            )
            tasks.append({
                'task_id': task.id,
                'filename': filename,
                'status_url': url_for('video.check_video_status', task_id=task.id, _external=True)
            })
            logger.info(f"Submitted task {task.id} for file {filename} for user {user.id}")
        except Exception as e:
            logger.error(f"Error submitting task for file '{filename}' for user {user.id}: {e}", exc_info=True)
            tasks.append({
                'task_id': None,
                'filename': filename,
                'error': f"Error submitting task: {str(e)}"
            })

    logger.info(
        f"User {user.id}: Submitted {len([t for t in tasks if t.get('task_id')])} tasks for video effects processing."
    )
    return jsonify({
        'success': len([t for t in tasks if t.get('task_id')]) > 0,
        'msg': f"Submitted {processed_files} file(s) for video effects processing with total duration {duration}s.",
        'tasks': tasks
    })


@jwt_required()
def check_video_status(task_id):
    logger.info(f"Checking status for video effects task ID: {task_id}")
    task_result = AsyncResult(task_id, app=celery)

    response = {
        'success': False,
        'task_id': task_id,
        'status': task_result.state,
        'completed': False,
        'msg': 'Task status unknown or processing...',
        'videos': []
    }

    if task_result.state == 'PENDING':
        logger.info(f"Video effects task is still pending: {task_id}")
        response.update({
            'success': True,
            'msg': 'Video effects generation is pending...'
        })
    elif task_result.state == 'SUCCESS':
        result = task_result.get()
        if result and isinstance(result, dict):
            generation_success = result.get('success', False)
            results_list = result.get('results', [])

            if generation_success and results_list:
                logger.info(f"Video effects task completed successfully: {task_id}")
                completed_videos = []
                all_successful = True

                for item in results_list:
                    if item.get('success'):
                        completed_videos.append({
                            'effect': item.get('effect'),
                            'url': item.get('url'),
                            'video_id': item.get('video_id')
                        })
                    else:
                        all_successful = False
                        logger.warning(
                            f"Task {task_id}: Sub-task for effect {item.get('effect')} failed. Error: {item.get('error')}")

                response.update({
                    'success': True,
                    'completed': True,
                    'msg': 'Video effects task completed.' + (
                        ' All videos processed successfully.' if all_successful else ' Some videos failed to generate or upload.'),
                    'videos': completed_videos
                })

            elif not generation_success:
                logger.error(
                    f"Video effects task {task_id} finished but reported failure. Error: {result.get('error')}")
                response.update({
                    'success': False,
                    'completed': True,
                    'msg': 'Video effects task finished but reported an internal failure.',
                    'error': result.get('error', 'Unknown error from task result')
                })
            else:
                logger.warning(f"Video effects task {task_id} succeeded but returned no results or an empty list.")
                response.update({
                    'success': True,
                    'completed': True,
                    'msg': result.get('error',
                                      'Video effects task completed, but no video results were generated (check input or task logs).'),
                    'videos': []
                })

        else:
            logger.error(
                f"Video effects task {task_id} succeeded but returned an invalid result format: {type(result)}")
            response.update({
                'success': False,
                'completed': True,
                'msg': 'Video effects task completed but returned an unexpected result format.',
                'error': 'Invalid result format received from task.'
            })

    elif task_result.state == 'FAILURE':
        logger.error(f"Video effects task failed: {task_id}. Traceback: {task_result.traceback}")
        response.update({
            'success': False,
            'completed': True,
            'msg': 'Video effects task failed during execution.',
            'error': str(task_result.info)
            # 'traceback': task_result.traceback # Optionally include traceback for debugging
        })
    elif task_result.state == 'RETRY':
        logger.info(f"Video effects task is being retried: {task_id}")
        response.update({
            'success': True,
            'msg': 'Video effects task is currently being retried...'
        })
    else:
        logger.warning(f"Video effects task {task_id} has an unexpected state: {task_result.state}")
        response.update({
            'success': False,
            'msg': f'Video effects task has an unexpected status: {task_result.state}'
        })

    return jsonify(response)


@jwt_required()
def generate_video_with_ffmpeg():
    user = get_user_from_jwt()
    if user is None:
        logger.error("Generate video effects failed: User not found.")
        raise ResourceNotFoundException("User not found")

    data = request.get_json()
    logger.info("Data received for video generation: %s", data)

    try:
        task = concat_video.apply_async(
            args=[user.id, data]
        )
        logger.info(f"Submitted video generation task {task.id} for user {user.id}")
        return jsonify({
            'success': True,
            'msg': 'Video generation task submitted successfully.',
            'task_id': task.id,
            'status_url': url_for('video.check_video_concat_status', task_id=task.id, _external=True)
        })
    except Exception as e:
        logger.error(f"Error submitting video generation task for user {user.id}: {e}", exc_info=True)
        raise InternalServerException("Error submitting video generation task for user {user.id}")


def check_video_concat_status(task_id):
    logger.info(f"Checking status for video concat task ID: {task_id}")
    task_result = AsyncResult(task_id, app=celery)

    response = {
        'success': False,
        'task_id': task_id,
        'status': task_result.state,
        'completed': False,
        'msg': 'Task status unknown or processing...',
        'video_url': None,
        'video_id': None
    }

    if task_result.state == 'PENDING':
        logger.info(f"Video concat task is still pending: {task_id}")
        response.update({
            'success': True,
            'msg': 'Video concatenation is pending...'
        })
    elif task_result.state == 'SUCCESS':
        result = task_result.get()
        if result and isinstance(result, dict) and result.get('success'):
            video_url = result.get('url')
            video_id_from_task = result.get('video_id')
            if video_url and video_id_from_task:
                logger.info(
                    f"Video concat task {task_id} completed successfully. URL: {video_url}, Video ID: {video_id_from_task}")
                response.update({
                    'success': True,
                    'completed': True,
                    'msg': 'Video concatenation task completed successfully.',
                    'video_url': video_url,
                    'video_id': video_id_from_task
                })
            else:
                logger.error(
                    f"Video concat task {task_id} succeeded but result is missing URL or video_id. Result: {result}")
                response.update({
                    'success': False,
                    'completed': True,
                    'msg': 'Video concatenation task completed, but necessary video information is missing.',
                    'error': 'Task result incomplete.'
                })
        elif result and isinstance(result, dict) and not result.get('success'):
            error_message = result.get('error', 'Video concatenation failed, reason not specified by task.')
            logger.error(
                f"Video concat task {task_id} completed but reported failure. Error: {error_message}. Result: {result}")
            response.update({
                'success': False,
                'completed': True,
                'msg': 'Video concatenation task reported a failure.',
                'error': error_message
            })
        else:
            logger.error(
                f"Video concat task {task_id} succeeded but returned an invalid result format: {type(result)}. Result: {result}")
            response.update({
                'success': False,
                'completed': True,
                'msg': 'Video concat task completed but returned an unexpected result format.',
                'error': 'Invalid result format received from task.'
            })
    elif task_result.state == 'FAILURE':
        logger.error(
            f"Video concat task failed: {task_id}. Info: {task_result.info}, Traceback: {task_result.traceback}")
        response.update({
            'success': False,
            'completed': True,
            'msg': 'Video concatenation task failed during execution.',
            'error': str(task_result.info)
        })
    elif task_result.state == 'RETRY':
        logger.info(f"Video concat task is being retried: {task_id}")
        response.update({
            'success': True,
            'msg': 'Video concatenation task is currently being retried...'
        })
    else:
        logger.warning(f"Video concat task {task_id} has an unexpected state: {task_result.state}")
        response.update({
            'success': False,
            'msg': f'Video concat task has an unhandled status: {task_result.state}.'
        })

    return jsonify(response)
