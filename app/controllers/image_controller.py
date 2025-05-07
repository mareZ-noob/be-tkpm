from celery.result import AsyncResult
from flask import jsonify, request, url_for
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename

from app.config.extensions import celery
from app.config.logging_config import setup_logging
from app.tasks.image_tasks import process_image_generation
from app.tasks.upload_tasks import upload_image_directly
from app.utils.constant import ALLOWED_IMAGE_EXTENSIONS
from app.utils.exceptions import BadRequestException, InternalServerException, MissingParameterException
from app.utils.function_helpers import allowed_file
from app.utils.jwt_helpers import get_user_id_from_jwt

logger = setup_logging()


@jwt_required()
def generate_image():
    data = request.get_json()

    required_fields = ['model', 'paragraph_id', 'content']
    for field in required_fields:
        if field not in data:
            logger.error(f"Generate image failed: Missing required field: {field}")
            raise MissingParameterException(f"Missing required field: {field}")

    user_id = get_user_id_from_jwt()
    if not user_id:
        logger.error("Generate image failed: JWT identity missing or invalid.")
        raise MissingParameterException("User not found or invalid token")

    model = data.get('model')
    paragraph_id = data.get('paragraph_id')
    content = data.get('content')
    num_images = data.get('num_images', 2)

    # Validate num_images
    if not isinstance(num_images, int) or num_images <= 0:
        logger.error(f"Generate image failed: Invalid number of images requested: {num_images}")
        raise MissingParameterException("Invalid number of images specified. Must be a positive integer.")

    try:
        task = process_image_generation.apply_async(args=[user_id, model, paragraph_id, content, num_images])

        if task and task.id:
            logger.info(f"Image generation task created successfully for user {user_id}. Task ID: {task.id}")
            status_url = url_for('image.check_image_status', task_id=task.id, _external=True)
            return jsonify({
                'success': True,
                'task_id': task.id,
                'msg': 'Image generation task created successfully.',
                'status_url': status_url
            })
        else:
            logger.error(f"Failed to create image generation task for user {user_id}.")
            raise InternalServerException("Failed to initiate image generation task.")

    except Exception as e:
        logger.error(f"Error submitting image generation task for user {user_id}: {e}", exc_info=True)
        raise InternalServerException(f"An error occurred while starting the image generation: {str(e)}")


@jwt_required()
def check_image_status(task_id):
    logger.debug(f"Checking status for image generation task ID: {task_id}")
    task_result = AsyncResult(task_id, app=celery)

    response = {
        'success': False,
        'task_id': task_id,
        'status': task_result.state,
        'completed': False,
        'msg': 'Task status unknown or processing...',
        'images': []
    }

    if task_result.state == 'PENDING':
        logger.info(f"Image generation task is still pending: {task_id}")
        response.update({
            'success': True,
            'msg': 'Image generation is pending...'
        })
    elif task_result.state == 'SUCCESS':
        result = task_result.get()
        if result and isinstance(result, dict):
            generation_success = result.get('success', False)
            results_list = result.get('results', [])

            if generation_success and results_list:
                logger.info(f"Image generation task completed successfully: {task_id}")
                completed_images = []
                all_successful = True

                for item in results_list:
                    if item.get('success'):
                        completed_images.append({
                            'paragraph_id': item.get('paragraph_id'),
                            'prompt': item.get('prompt'),
                            'url': item.get('url'),
                            'image_id': item.get('image_id')
                            # 'public_id' could also be added if needed from the result
                        })
                    else:
                        # If any item failed, mark the overall process as partially failed
                        all_successful = False
                        logger.warning(
                            f"Task {task_id}: Sub-task for paragraph {item.get('paragraph_id')} failed. Error: {item.get('error')}")
                # --- END MODIFIED LOGIC ---

                response.update({
                    'success': True,
                    'completed': True,
                    'msg': 'Image generation task completed.' + (
                        ' All images processed successfully.' if all_successful else ' Some images failed to generate or upload.'),
                    'images': completed_images
                })

            elif not generation_success:
                logger.error(
                    f"Image generation task {task_id} finished but reported failure. Error: {result.get('error')}")
                response.update({
                    'success': False,
                    'completed': True,
                    'msg': 'Image generation task finished but reported an internal failure.',
                    'error': result.get('error', 'Unknown error from task result')
                })
            else:
                logger.warning(f"Image generation task {task_id} succeeded but returned no results.")
                response.update({
                    'success': True,
                    'completed': True,
                    'msg': 'Image generation task completed, but no image results were returned.',
                    'images': []
                })

        else:
            logger.error(
                f"Image generation task {task_id} succeeded but returned an invalid result format: {type(result)}")
            response.update({
                'success': False,
                'completed': True,
                'msg': 'Image generation task completed but returned an unexpected result format.',
                'error': 'Invalid result format received from task.'
            })

    elif task_result.state == 'FAILURE':
        logger.error(f"Image generation task failed: {task_id}. Traceback: {task_result.traceback}")
        response.update({
            'success': False,
            'completed': True,
            'msg': 'Image generation task failed during execution.',
            'error': str(task_result.traceback)
        })
    elif task_result.state == 'RETRY':
        logger.info(f"Image generation task is being retried: {task_id}")
        response.update({
            'success': True,
            'msg': 'Image generation task is currently being retried...'
        })
    else:
        logger.warning(f"Image generation task {task_id} has an unexpected state: {task_result.state}")
        response.update({
            'success': False,
            'msg': f'Image generation task has an unexpected status: {task_result.state}'
        })

    return jsonify(response)


@jwt_required()
def upload_user_images():
    user_id = get_user_id_from_jwt()
    if not user_id:
        logger.error("Sync Upload user images failed: JWT identity missing or invalid.")
        raise MissingParameterException("User not found or invalid token")

    if 'images' not in request.files:
        logger.error(f"Sync Upload user images failed for user {user_id}: No 'images' file part.")
        raise BadRequestException("No file part named 'images' in the request.")

    files = request.files.getlist('images')

    if not files or all(f.filename == '' for f in files):
        logger.error(f"Sync Upload user images failed for user {user_id}: No files selected.")
        raise BadRequestException("No files selected for upload.")

    results = []
    processed_files = 0
    successful_uploads = 0

    logger.info(f"Sync Upload: Received {len(files)} file(s) for synchronous upload from user {user_id}.")

    for file in files:
        if file and file.filename and allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
            filename = secure_filename(file.filename)
            try:
                file_data = file.read()

                result = upload_image_directly(user_id, file_data, filename)
                results.append(result)

                if result.get('success'):
                    successful_uploads += 1
                processed_files += 1

            except Exception as e:
                logger.error(f"Sync Upload: Error reading file '{filename}' for user {user_id}: {e}", exc_info=True)
                results.append({'success': False, 'filename': filename, 'error': f"Error reading file: {str(e)}"})
                processed_files += 1

        elif file and file.filename:
            filename = secure_filename(file.filename)
            logger.warning(f"Sync Upload: Skipping file with disallowed extension: {filename} for user {user_id}")
            results.append({
                'success': False,
                'filename': filename,
                'error': f"File type not allowed. Allowed types: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"
            })
            processed_files += 1

    if processed_files == 0:
        logger.error(f"User {user_id}: No files were processed.")
        raise BadRequestException("No files were processed for upload.")

    logger.info(f"User {user_id}: Synchronous upload request processed. {successful_uploads}/{processed_files} images uploaded successfully.")
    return jsonify({
        'success': successful_uploads > 0,
        'msg': f"Processed {processed_files} file(s). {successful_uploads} uploaded successfully.",
        'results': results
    })
