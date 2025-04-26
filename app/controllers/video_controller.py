from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.config.extensions import db
from app.config.logging_config import setup_logging
from app.models import Video
from app.utils.exceptions import ResourceNotFoundException
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
