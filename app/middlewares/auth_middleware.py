# Not used

from functools import wraps

import jwt
from flask import jsonify, request

from app.models.user import User

SECRET_KEY = 'secret'


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")
        print(f"Token: {token}")  # Debug token
        if not token:
            return jsonify({"message": "Token is missing!"}), 401

        try:
            decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            user = User.query.get(decoded["user_id"])
            if not user:
                return jsonify({"message": "User not found"}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Token expired"}), 401
        except jwt.InvalidTokenError as e:
            print(f"JWT Error: {str(e)}")  # Debug lỗi
            return jsonify({"message": "Invalid token"}), 401

        return f(user, *args, **kwargs)

    return decorated
