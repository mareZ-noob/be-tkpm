from flask import Blueprint

from app.controllers.auth_controller import (
    change_password,
    forgot_password,
    login,
    logout,
    refresh,
    register,
    reset_password,
)

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

auth_bp.route('/login', methods=['POST'])(login)
auth_bp.route('/register', methods=['POST'])(register)
auth_bp.route('/refresh', methods=['POST'])(refresh)
auth_bp.route('/logout', methods=['POST'])(logout)
auth_bp.route('/forgot-password', methods=['POST'])(forgot_password)
auth_bp.route('/reset-password', methods=['POST'])(reset_password)
auth_bp.route('/change-password', methods=['POST'])(change_password)
