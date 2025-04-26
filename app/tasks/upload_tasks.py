import logging
import uuid

import cloudinary.uploader

from app.config.extensions import celery, db
from app.config.logging_config import setup_logging
from app.models import Audio, User, Video
from app.utils.constant import AUDIO_FOLDER, AVATAR_FOLDER, VIDEO_FOLDER

setup_logging()
logger = logging.getLogger(__name__)


@celery.task(bind=True, max_retries=3)
def process_avatar_upload(self, user_id, file_data):
    task_id = self.request.id
    logger.info(f"[Task ID: {task_id}] Starting avatar upload task for user_id: {user_id}")
    try:
        unique_id = str(uuid.uuid4())
        public_id = f"{AVATAR_FOLDER}/{user_id}/{unique_id}"

        logger.info(
            f"[Task ID: {task_id}] Attempting to upload avatar for user {user_id} to Cloudinary (public_id: {public_id}).")
        upload_result = cloudinary.uploader.upload(
            file_data,
            resource_type="image",
            public_id=public_id,
            overwrite=True,
            format="png",
            transformation=[
                {"width": 500, "height": 500, "crop": "limit"}
            ]
        )
        secure_url = upload_result['secure_url']
        logger.info(
            f"[Task ID: {task_id}] Successfully uploaded avatar for user {user_id}. Cloudinary URL: {secure_url}")

        logger.info(f"[Task ID: {task_id}] Attempting to update avatar URL for user {user_id} in the database.")
        with db.session.begin():
            user = User.query.get(user_id)
            if not user:
                logger.error(f"[Task ID: {task_id}] User not found in database for user_id: {user_id}")
                raise Exception(f"User not found for user_id: {user_id}")

            user.avatar = secure_url
            db.session.commit()

        logger.info(f"[Task ID: {task_id}] Successfully updated avatar URL for user {user_id} in the database.")
        logger.info(f"[Task ID: {task_id}] Avatar upload task completed successfully for user_id: {user_id}.")
        return {'msg': 'success', 'url': secure_url}

    except Exception as exc:
        logger.error(f"[Task ID: {task_id}] Exception occurred during avatar upload for user {user_id}. Error: {exc}")
        try:
            retry_count = self.request.retries + 1
            logger.error(
                f"[Task ID: {task_id}] Retrying avatar upload for user {user_id}... Attempt {retry_count}/{self.max_retries}. Countdown: 5s.")
            self.retry(exc=exc, countdown=5)
        except self.MaxRetriesExceededError as e:
            logger.error(
                f"[Task ID: {task_id}] Avatar upload failed permanently for user {user_id} after {self.max_retries} retries. Error: {e}")
            return {'msg': 'failed', 'error': f"Max retries exceeded: {str(e)}"}
        except Exception as retry_exc:
            logger.error(
                f"[Task ID: {task_id}] An unexpected error occurred during the retry mechanism for user {user_id}. Error: {retry_exc}")
            return {'msg': 'failed', 'error': f"Retry mechanism failed: {str(retry_exc)}"}


@celery.task(bind=True, max_retries=3)
def process_video_upload(self, user_id, file_data, filename, title=None):
    task_id = self.request.id
    logger.info(f"[Task ID: {task_id}] Starting video upload task for user_id: {user_id}, filename: {filename}")
    try:
        unique_id = str(uuid.uuid4())
        public_id = f"{VIDEO_FOLDER}/{user_id}/{unique_id}"

        logger.info(
            f"[Task ID: {task_id}] Attempting to upload video '{filename}' for user {user_id} to Cloudinary (public_id: {public_id}).")
        upload_result = cloudinary.uploader.upload(
            file_data,
            resource_type="video",
            public_id=public_id,
            overwrite=True,
            chunk_size=6000000  # 6MB chunks for large files
        )
        secure_url = upload_result['secure_url']
        logger.info(
            f"[Task ID: {task_id}] Successfully uploaded video '{filename}' for user {user_id}. Cloudinary URL: {secure_url}")

        video_title = title or filename
        logger.info(
            f"[Task ID: {task_id}] Attempting to add video record for user {user_id} (Title: '{video_title}') to the database.")
        with db.session.begin():
            video = Video(
                user_id=user_id,
                url=secure_url,
                title=video_title
            )
            db.session.add(video)
            db.session.commit()

        logger.info(f"[Task ID: {task_id}] Successfully added video record for user {user_id} to the database.")
        logger.info(
            f"[Task ID: {task_id}] Video upload task completed successfully for user_id: {user_id}, filename: {filename}.")
        return {'msg': 'success', 'url': secure_url}

    except Exception as exc:
        logger.error(
            f"[Task ID: {task_id}] Exception occurred during video upload for user {user_id}, filename: {filename}. Error: {exc}")
        try:
            retry_count = self.request.retries + 1
            logger.error(
                f"[Task ID: {task_id}] Retrying video upload for user {user_id}, filename: {filename}... Attempt {retry_count}/{self.max_retries}. Countdown: 5s.")
            self.retry(exc=exc, countdown=5)
        except self.MaxRetriesExceededError as e:
            logger.error(
                f"[Task ID: {task_id}] Video upload failed permanently for user {user_id}, filename: {filename} after {self.max_retries} retries. Error: {e}")
            return {'msg': 'failed', 'error': f"Max retries exceeded: {str(e)}"}
        except Exception as retry_exc:
            logger.error(
                f"[Task ID: {task_id}] An unexpected error occurred during the retry mechanism for user {user_id}, filename: {filename}. Error: {retry_exc}")
            return {'msg': 'failed', 'error': f"Retry mechanism failed: {str(retry_exc)}"}


@celery.task(bind=True, max_retries=3)
def process_audio_upload(self, user_id, file_data, filename):
    task_id = self.request.id
    logger.info(f"[Task ID: {task_id}] Starting audio upload task for user_id: {user_id}, filename: {filename}")
    try:
        unique_id = str(uuid.uuid4())
        public_id = f"{AUDIO_FOLDER}/{user_id}/{unique_id}"

        logger.info(
            f"[Task ID: {task_id}] Attempting to upload audio '{filename}' for user {user_id} to Cloudinary (public_id: {public_id}, resource_type: video).")
        upload_result = cloudinary.uploader.upload(
            file_data,
            resource_type="video",
            public_id=public_id,
            overwrite=True,
            chunk_size=3000000  # 3MB chunks
        )
        secure_url = upload_result['secure_url']
        logger.info(
            f"[Task ID: {task_id}] Successfully uploaded audio '{filename}' for user {user_id}. Cloudinary URL: {secure_url}")

        logger.info(
            f"[Task ID: {task_id}] Attempting to add audio record for user {user_id} (Title: '{filename}') to the database.")
        with db.session.begin():
            audio = Audio(
                user_id=user_id,
                url=secure_url,
                title=filename
            )
            db.session.add(audio)
            db.session.commit()

        logger.info(f"[Task ID: {task_id}] Successfully added audio record for user {user_id} to the database.")
        logger.info(
            f"[Task ID: {task_id}] Audio upload task completed successfully for user_id: {user_id}, filename: {filename}.")
        return {'msg': 'success', 'url': secure_url}

    except Exception as exc:
        logger.error(
            f"[Task ID: {task_id}] Exception occurred during audio upload for user {user_id}, filename: {filename}. Error: {exc}")
        try:
            retry_count = self.request.retries + 1
            logger.error(
                f"[Task ID: {task_id}] Retrying audio upload for user {user_id}, filename: {filename}... Attempt {retry_count}/{self.max_retries}. Countdown: 5s.")
            self.retry(exc=exc, countdown=5)
        except self.MaxRetriesExceededError as e:
            logger.error(
                f"[Task ID: {task_id}] Audio upload failed permanently for user {user_id}, filename: {filename} after {self.max_retries} retries. Error: {e}")
            return {'msg': 'failed', 'error': f"Max retries exceeded: {str(e)}"}
        except Exception as retry_exc:
            logger.error(
                f"[Task ID: {task_id}] An unexpected error occurred during the retry mechanism for user {user_id}, filename: {filename}. Error: {retry_exc}")
            return {'msg': 'failed', 'error': f"Retry mechanism failed: {str(retry_exc)}"}
