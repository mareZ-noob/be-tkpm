from flask import Blueprint, jsonify, request
from app.models.user import User, db
from app.controllers.user_controller import add_user, get_users
import jwt
import datetime


auth_bp = Blueprint('auth', __name__, url_prefix='/')

SECRET_KEY = 'secret'

@auth_bp.route('/login', methods=['POST'])
def login(): 
    data = request.json
    required_fields = ['username', 'password']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400
    user = User.query.filter_by(username=data['username']).first()
    if not user or not user.check_password(data['password']):
        return jsonify({'error': 'Invalid username or password'}), 401
    token_payload = {
        'user_id': user.id,
        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    }
    token = jwt.encode(token_payload, SECRET_KEY, algorithm="HS256")
    print(f"Token: {token}")
    return jsonify({'token': token, "user": user.to_dict()}), 200


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.json
    
    required_fields = ['username', 'email', 'password']
    
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400
    
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 400
    
    if  User.query.filter_by(email=data['email']).first():
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
