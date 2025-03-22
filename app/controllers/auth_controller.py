import logging
from flask import jsonify, request
from flask_jwt_extended import (
    create_access_token, create_refresh_token, decode_token,
    get_jwt_identity, jwt_required, unset_jwt_cookies
)
from app.models.user import User, db
from app.utils.jwt_helpers import revoked_store  # Import hệ thống lưu JTI bị thu hồi

def login():
    data = request.json
    required_fields = ['username', 'password']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400

    user = User.query.filter_by(username=data['username']).first()
    if not user or not user.check_password(data['password']):
        return jsonify({'error': 'Invalid username or password'}), 401

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    logging.info("Access token: %s", access_token)
    logging.info("Refresh token: %s", refresh_token)

    response = jsonify({
        "user": user.to_dict(),
        "access_token": access_token
    })
    response.set_cookie(
        key='refresh_token',
        value=refresh_token,
        httponly=True,
        secure=False,  # Dùng `True` trong môi trường production với HTTPS
        samesite='Strict',
        path='/',
        max_age=30 * 24 * 60 * 60
    )
    return response, 200


def register():
    data = request.json
    required_fields = ['username', 'email', 'password']

    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400

    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 400

    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already exists'}), 400

    user = User(
        username=data['username'],
        email=data['email'],
        password=data['password']
    )
    user.hash_password(data['password'])  # Mã hóa mật khẩu

    db.session.add(user)
    db.session.commit()

    return jsonify(user.to_dict()), 201


@jwt_required(refresh=True)
def refresh():
    current_user = get_jwt_identity()
    access_token = create_access_token(identity=current_user)

    return jsonify({"access_token": access_token}), 200


@jwt_required()
def logout():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing access token"}), 401

    access_token = auth_header.split(" ")[1]
    try:
        decoded_token = decode_token(access_token)
        jti = decoded_token["jti"]
    except Exception:
        return jsonify({"error": "Invalid access token"}), 401

    revoked_store.add(jti)
    response = jsonify({"message": "Logged out"})
    unset_jwt_cookies(response)
    return response, 200
