from celery.result import AsyncResult
from flask import jsonify, request, url_for
from flask_jwt_extended import jwt_required

from app.config.extensions import celery
from app.config.logging_config import setup_logging
from app.tasks.image_tasks import process_image_generation
from app.utils.exceptions import InternalServerException, MissingParameterException
from app.utils.jwt_helpers import get_user_id_from_jwt

logger = setup_logging()


@jwt_required()
def generate_image():
    data = request.get_json()

    required_fields = ['model', 'paragraph_id', 'content']
    for field in required_fields:
        if field not in data:
            logger.error("Generate image failed: Missing required field: " + field)
            raise MissingParameterException("Missing required field: " + field)

    user_id = get_user_id_from_jwt()
    if not user_id:
        logger.error("Paragraph audio upload failed: JWT identity missing.")
        raise MissingParameterException("User not found or invalid token")

    model = data.get('model')
    paragraph_id = data.get('paragraph_id')
    content = data.get('content')
    num_images = data.get('num_images', 2)

    if not isinstance(num_images, int) or num_images <= 0:
        logger.error("Generate image failed: Invalid number of images.")
        raise MissingParameterException("Invalid number of images")

    task = process_image_generation.apply_async(args=[user_id, model, paragraph_id, content, num_images])

    if task:
        logger.info(f"Image generation task created with task ID: {task.id}")
        status_url = url_for('image.check_image_status', task_id=task.id, _external=True)
        return jsonify({
            'success': True,
            'task_id': task.id,
            'msg': 'Image generation task created successfully',
            'status_url': status_url
        })
    else:
        logger.error("Failed to create image generation task")
        raise InternalServerException("Failed to create image generation task")


@jwt_required()
def check_image_status(task_id):
    logger.debug(f"Checking status for image generation task ID: {task_id}")
    task_result = AsyncResult(task_id, app=celery)

    if task_result.state == 'PENDING':
        logger.info(f"Image generation task is still pending: {task_id}")
        response = {
            'success': True,
            'task_id': task_id,
            'status': task_result.state,
            'completed': False,
            'msg': 'Image generation is pending...'
        }
    elif task_result.state == 'SUCCESS':
        result = task_result.get()
        if result and result.get('success'):
            logger.info(f"Image generation task completed with task ID: {task_id}")
            all_uploads_complete = True
            completed_images = []
            pending_upload_tasks = []

            for item in result.get('results', []):
                if item.get('success') and 'upload_task_id' in item:
                    upload_task_id = item['upload_task_id']
                    upload_result = AsyncResult(upload_task_id, app=celery)

                    if upload_result.state == 'SUCCESS':
                        upload_data = upload_result.get()
                        if upload_data and upload_data.get('success'):
                            logger.info(f"Image generation task completed successfully: {upload_task_id}")
                            completed_images.append({
                                'paragraph_id': item['paragraph_id'],
                                'prompt': item['response'],
                                'url': upload_data.get('url'),
                                'public_id': upload_data.get('public_id'),
                                'image_id': upload_data.get('id')
                            })
                        else:
                            logger.error(f"Image generation task failed: Upload task {upload_task_id} failed.")
                            all_uploads_complete = False
                            pending_upload_tasks.append({
                                'task_id': upload_task_id,
                                'status': 'FAILED',
                                'error': upload_data.get('error') if upload_data else 'Unknown error'
                            })
                    elif upload_result.state in ['PENDING', 'RETRY']:
                        logger.info(
                            f"Image generation task is still processing: Upload task {upload_task_id} is {upload_result.state}.")
                        all_uploads_complete = False
                        pending_upload_tasks.append({
                            'task_id': upload_task_id,
                            'status': upload_result.state
                        })
                    else:
                        logger.error(f"Image generation task failed: Upload task {upload_task_id} failed.")
                        all_uploads_complete = False
                        pending_upload_tasks.append({
                            'task_id': upload_task_id,
                            'status': 'FAILED',
                            'error': str(upload_result.traceback) if upload_result.traceback else 'Unknown error'
                        })
                elif not item.get('success'):
                    logger.error("Image generation task failed: Image generation failed.")
                    pass

            response = {
                'success': True,
                'task_id': task_id,
                'status': task_result.state,
                'completed': all_uploads_complete,
                'msg': 'Image generation completed' + (
                    ' and all uploads finished' if all_uploads_complete else ', uploads in progress'),
                'images': completed_images
            }

            if not all_uploads_complete and pending_upload_tasks:
                response['pending_uploads'] = pending_upload_tasks

        else:
            response = {
                'success': False,
                'task_id': task_id,
                'status': task_result.state,
                'completed': False,
                'msg': 'Image generation failed',
                'error': result.get('error') if result else 'Unknown error'
            }
    elif task_result.state == 'FAILURE':
        response = {
            'success': False,
            'task_id': task_id,
            'status': task_result.state,
            'completed': False,
            'msg': 'Image generation failed',
            'error': str(task_result.traceback)
        }
    elif task_result.state == 'RETRY':
        response = {
            'success': True,
            'task_id': task_id,
            'status': task_result.state,
            'completed': False,
            'msg': 'Image generation is being retried...'
        }
    else:
        response = {
            'success': False,
            'task_id': task_id,
            'status': task_result.state,
            'completed': False,
            'msg': 'Unknown task status'
        }

    return jsonify(response)
