from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError

from app.config.extensions import db
from app.config.logging_config import setup_logging
from app.models import User
from app.utils.exceptions import InternalServerException, ResourceNotFoundException
from app.utils.jwt_helpers import get_user_from_jwt

logger = setup_logging()


@jwt_required()
def get_users():
    users = User.query.all()
    logger.info(f"Found {len(users)} users")
    return jsonify({"users": [user.to_dict() for user in users]}), 200


@jwt_required()
def get_profile():
    user = get_user_from_jwt()
    if user is None:
        logger.error("Get profile failed: User not found.")
        raise ResourceNotFoundException("User not found")
    logger.info(f"Get user profile: {user}")
    return jsonify(user.to_dict()), 200


@jwt_required()
def update_profile():
    user = get_user_from_jwt()
    if user is None:
        logger.error("Update user failed: User not found.")
        raise ResourceNotFoundException("User not found")

    data = request.get_json()

    first_name = data.get('first_name', '')
    last_name = data.get('last_name', '')
    date_of_birth = data.get('date_of_birth', '')
    description = data.get('description', '')

    try:
        user.first_name = first_name
        user.last_name = last_name
        user.date_of_birth = date_of_birth
        user.description = description

        db.session.commit()
        logger.info(f"Update user profile: {user}")
        return jsonify(user.to_dict()), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Error updating user: {e}", exc_info=True)
        raise InternalServerException("Error updating user")


@jwt_required()
def delete_user():
    user = get_user_from_jwt()
    if user is None:
        logger.error("Delete user failed: User not found.")
        raise ResourceNotFoundException("User not found")

    try:
        logger.info(f"Delete user: {user}")
        db.session.delete(user)
        db.session.commit()
        return jsonify({"msg": "User deleted successfully"}), 200
    except SQLAlchemyError:
        db.session.rollback()
        logger.error("Error deleting user", exc_info=True)
        raise InternalServerException("Error deleting user")
