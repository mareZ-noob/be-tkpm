from flask import Blueprint, jsonify, request

from app.controllers.user_controller import add_user, get_users
from app.middlewares.auth_middleware import token_required  # 📌 Import middleware xác thực

user_bp = Blueprint('user', __name__, url_prefix='/users')


@user_bp.route('/', methods=['GET'])
def list_users():
    users = get_users()
    return jsonify([{"id": u.id, "username": u.username, "email": u.email} for u in users])


@user_bp.route('/', methods=['POST'])
def create_user():
    data = request.get_json()

    username = data.get('username')
    password = data.get('password')
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    email = data.get('email')
    date_of_birth = data.get('date_of_birth', None)  # Default to None if missing
    description = data.get('description', '')

    if not username or not password or not first_name or not last_name or not email:
        return jsonify({"error": "Missing required fields"}), 400

    user = add_user(
        username=username,
        password=password,
        first_name=first_name,
        last_name=last_name,
        email=email,
        date_of_birth=date_of_birth,
        description=description
    )

    if not user:
        return jsonify({"error": "User already exists"}), 400

    return jsonify(user.to_dict()), 201


@user_bp.route('/profile', methods=['GET'])
@token_required
def get_profile(user):
    return jsonify(user.to_dict()), 200