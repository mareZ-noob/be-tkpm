from flask import Blueprint

from app.controllers.user_controller import get_profile, get_users, update_profile

user_bp = Blueprint('user', __name__, url_prefix='/users')

user_bp.route('/', methods=['GET'])(get_users)
user_bp.route('/profile', methods=['GET'])(get_profile)
user_bp.route('/profile', methods=['PUT'])(update_profile)
