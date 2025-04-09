import cloudinary.uploader

from app.config.extensions import celery, db
from app.models import User, Video
from app.utils.constant import AVATAR_FOLDER, VIDEO_FOLDER


@celery.task(bind=True, max_retries=3)
def process_avatar_upload(self, user_id, file_data, filename):
    try:
        upload_result = cloudinary.uploader.upload(
            file_data,
            resource_type="image",
            public_id=f"{AVATAR_FOLDER}/{user_id}/{filename.rsplit('.', 1)[0]}",
            overwrite=True,
            format="png",
            transformation=[
                {"width": 500, "height": 500, "crop": "limit"}
            ]
        )

        with db.session.begin():
            user = User.query.get(user_id)
            if not user:
                raise Exception("User not found")

            user.avatar = upload_result['secure_url']
            db.session.commit()

        return {'msg': 'success', 'url': upload_result['secure_url']}

    except Exception as exc:
        try:
            self.retry(exc=exc, countdown=5)
        except self.MaxRetriesExceededError as e:
            return {'msg': 'failed', 'error': str(e)}


@celery.task(bind=True, max_retries=3)
def process_video_upload(self, user_id, file_data, filename, title=None):
    try:
        upload_result = cloudinary.uploader.upload(
            file_data,
            resource_type="video",
            public_id=f"{VIDEO_FOLDER}/{user_id}/{filename.rsplit('.', 1)[0]}",
            overwrite=True,
            chunk_size=6000000  # 6MB chunks for large files
        )

        with db.session.begin():
            video = Video(
                user_id=user_id,
                url=upload_result['secure_url'],
                title=title or filename
            )
            db.session.add(video)
            db.session.commit()

        return {'msg': 'success', 'url': upload_result['secure_url']}

    except Exception as exc:
        try:
            self.retry(exc=exc, countdown=5)
        except self.MaxRetriesExceededError as e:
            return {'msg': 'failed', 'error': str(e)}
