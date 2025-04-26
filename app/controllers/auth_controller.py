from datetime import datetime, timezone

from flask import jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_jwt_identity,
    jwt_required,
    unset_jwt_cookies,
)

from app.config.extensions import db, limiter
from app.config.logging_config import setup_logging
from app.models import ResetPasswordToken, User
from app.tasks.email_tasks import send_email_task
from app.utils.constant import FRONTEND_URL
from app.utils.exceptions import (
    BadRequestException,
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    InvalidTokenException,
    MissingParameterException,
    ResourceNotFoundException,
    UsernameAlreadyExistsException,
)
from app.utils.jwt_helpers import get_user_from_jwt, revoked_store

logger = setup_logging()


def login():
    data = request.json
    required_fields = ['username', 'password']

    if not all(field in data for field in required_fields):
        logger.error("Login failed: Missing username or password field.")
        raise MissingParameterException("Missing required fields: {}".format(", ".join(required_fields)))

    user = User.query.filter_by(username=data['username']).first()
    if not user or not user.check_password(data['password']):
        logger.error("Login failed: Invalid username or password.")
        raise InvalidCredentialsException("Invalid username or password")

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    logger.info("User logged in successfully: %s", user.username)

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
        logger.error("Register failed: Missing username or password field.")
        raise MissingParameterException("Missing required fields: {}".format(", ".join(required_fields)))

    if User.query.filter_by(username=data['username']).first():
        logger.error("Register failed: Username already exists.")
        raise UsernameAlreadyExistsException("Username already exists")

    if User.query.filter_by(email=data['email']).first():
        logger.error("Register failed: Email already exists.")
        raise EmailAlreadyExistsException("Email already exists")

    user = User(
        username=data['username'],
        email=data['email'],
        password=data['password']
    )
    user.hash_password(data['password'])

    db.session.add(user)
    db.session.commit()

    return jsonify(user.to_dict()), 201


@jwt_required(refresh=True)
def refresh():
    current_user = get_jwt_identity()
    access_token = create_access_token(identity=current_user)
    logger.info(f"Refreshing access token for user {current_user}")
    return jsonify({"access_token": access_token}), 200


@jwt_required()
def logout():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.error("Logout failed: Missing authorization header.")
        raise BadRequestException("Missing authorization header")

    access_token = auth_header.split(" ")[1]
    try:
        decoded_token = decode_token(access_token)
        jti = decoded_token["jti"]
    except Exception as e:
        logger.error(f"Unexpected error during logout: {e}", exc_info=True)
        raise InvalidCredentialsException("Invalid token")

    revoked_store.add(jti)
    response = jsonify({"msg": "Logged out"})
    unset_jwt_cookies(response)
    return response, 200


def get_email_key():
    data = request.get_json()
    return data.get('email', 'anonymous')


@limiter.limit("3 per hour", key_func=get_email_key)
def forgot_password():
    data = request.get_json()
    email = data.get('email')

    if not email:
        logger.error("Forgot password failed: Missing email.")
        raise BadRequestException("Missing email")

    user = User.query.filter_by(email=email).first()
    if not user:
        logger.error("Forgot password failed: User not found.")
        raise ResourceNotFoundException("User not found")

    token = ResetPasswordToken.create_reset_password_token(user.id)

    reset_token = ResetPasswordToken(user_id=user.id, token=token)
    db.session.add(reset_token)
    db.session.commit()

    url = f"{FRONTEND_URL}/reset-password?token={token}"
    subject = "Password Reset Request - saikou"

    body = f"""Dear User,

    We have received a request to reset your password for your saikou account. 
    To proceed with resetting your password, please click the link below:

    {url}

    This link will expire in 1 hour for security purposes. If you did not request a password reset, 
    please disregard this email or contact our support team at saikou@gmail.com.

    Thank you,
    The saikou Team
    """

    # HTML version for better formatting
    html = f"""<!DOCTYPE html>
    <html>
    <head>
        <style>
            .container {{ max-width: 600px; margin: 0 auto; font-family: Arial, sans-serif; }}
            .header {{ color: #333; padding: 20px 0; }}
            .content {{ line-height: 1.6; color: #444; }}
            .button {{ 
                background-color: #007bff; 
                color: white; 
                padding: 10px 20px; 
                text-decoration: none; 
                border-radius: 5px; 
                display: inline-block;
            }}
            .footer {{ font-size: 12px; color: #777; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>Password Reset Request</h2>
            </div>
            <div class="content">
                <p>Dear User,</p>
                <p>We have received a request to reset your password for your saikou account. To proceed with resetting your password, please click the button below:</p>
                <p>
                    <a href="{url}" class="button">Reset Password</a>
                </p>
                <p>This link will expire in 1 hour for security purposes. If you did not request a password reset, please disregard this email or contact our support team at <a href="mailto:saikou@gmail.com">saikou@gmail.com</a>.</p>
                <p>Thank you,<br>The saikou Team</p>
            </div>
            <div class="footer">
                <p>&copy; {datetime.now().year} saikou. All rights reserved.</p>
                <p>227 Nguyen Van Cu | 0923820719</p>
            </div>
        </div>
    </body>
    </html>
    """

    task = send_email_task.delay(subject=subject, recipients=[email], body=body, html=html)
    logger.info(f"Email sent: {task}")

    return jsonify({
        'msg': 'Password reset email sent',
        'task_id': task.id
    }), 200


def reset_password():
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('new_password')

    if not token or not new_password:
        logger.error("Reset password failed: Missing token or new password.")
        raise MissingParameterException("Missing required parameters: token and new_password")

    reset_token = ResetPasswordToken.query.filter_by(token=token).first()
    if not reset_token:
        logger.error("Reset password failed: Token not found.")
        raise ResourceNotFoundException("Token not found")

    if reset_token.expired_at < datetime.now(timezone.utc):
        db.session.delete(reset_token)
        db.session.commit()
        logger.error("Reset password failed: Token expired.")
        raise InvalidTokenException("Token expired")

    user = User.query.get(reset_token.user_id)
    if not user:
        logger.error("Reset password failed: User not found.")
        raise ResourceNotFoundException("User not found")

    user.hash_password(new_password)
    db.session.commit()

    db.session.delete(reset_token)
    db.session.commit()

    return jsonify({'msg': 'Password reset successfully'}), 200


@jwt_required()
def change_password():
    data = request.get_json()
    user = get_user_from_jwt()
    if user is None:
        logger.error("Change password failed: User not found.")
        raise ResourceNotFoundException("User not found")

    old_password = data.get('old_password')
    new_password = data.get('new_password')

    if not old_password or not new_password:
        logger.error("Change password failed: Missing old password.")
        raise MissingParameterException("Missing required parameters: old_password and new_password")

    if not user.check_password(old_password):
        logger.error("Change password failed: Old password is incorrect.")
        raise InvalidCredentialsException("Old password is incorrect")

    user.hash_password(new_password)
    db.session.commit()

    return jsonify({'msg': 'Password changed successfully'}), 200
