from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError

from app.config.extensions import db
from app.models.user import User


@jwt_required()
def get_users():
    users = User.query.all()
    return jsonify({"users": [user.to_dict() for user in users]}), 200


@jwt_required()
def get_profile():
    current_user = get_jwt_identity()
    user = User.query.get(current_user)
    return jsonify(user.to_dict()), 200


@jwt_required()
def update_profile():
    current_user = get_jwt_identity()
    if not current_user:
        return jsonify({"msg": "User not found"}), 404

    user = User.query.get(current_user)

    if not user:
        return jsonify({"msg": "User not found"}), 404

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
        return jsonify(user.to_dict()), 200
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"msg": "Error updating user"}), 500


@jwt_required()
def delete_user():
    current_user = get_jwt_identity()
    if not current_user:
        return jsonify({"msg": "User ID not provided"}), 400
    user = User.query.get(current_user)

    try:
        db.session.delete(user)
        db.session.commit()
        return jsonify({"msg": "User deleted successfully"}), 200
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"msg": "Error deleting user"}), 500
