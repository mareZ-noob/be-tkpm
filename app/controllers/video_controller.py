from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.config.extensions import db
from app.models import User, Video


@jwt_required()
def create_video():
    data = request.get_json()
    current_user = get_jwt_identity()
    url = data.get('url')
    title = data.get('title', 'Untitled')

    if not current_user or not url:
        return jsonify({"msg": "Missing id or content"}), 400

    new_video = Video(user_id=current_user, url=url, title=title)
    db.session.add(new_video)
    db.session.commit()

    return jsonify(new_video.to_dict()), 201


@jwt_required()
def update_video(video_id):
    video = Video.query.get(video_id)
    if not video:
        return jsonify({"msg": "Video not found"}), 404

    data = request.get_json()
    video.from_dict(data)
    db.session.commit()

    return jsonify(video.to_dict())


@jwt_required()
def delete_video(video_id):
    video = Video.query.get(video_id)
    if not video:
        return jsonify({"msg": "Video not found"}), 404

    db.session.delete(video)
    db.session.commit()

    return jsonify({"msg": "Video deleted"}), 200


@jwt_required()
def get_user_videos():
    current_user = get_jwt_identity()
    user = User.query.get(current_user)
    if not user:
        return jsonify({"msg": "User not found"}), 404
    videos = Video.query.filter_by(user_id=user.id).all()
    return jsonify([video.to_dict() for video in videos])


@jwt_required()
def duplicate_video(video_id):
    video = Video.query.get(video_id)
    if not video:
        return jsonify({"msg": "Video not found"}), 404

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

    return jsonify(new_video.to_dict()), 201
