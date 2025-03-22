from flask import Blueprint
from app.controllers.auth_controller import login, register, refresh, logout

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

auth_bp.route('/login', methods=['POST'])(login)
auth_bp.route('/register', methods=['POST'])(register)
auth_bp.route('/refresh', methods=['POST'])(refresh)
auth_bp.route('/logout', methods=['POST'])(logout)
