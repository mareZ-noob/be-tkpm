from flask_jwt_extended import get_jwt_identity

from app.config.extensions import jwt
from app.config.logging_config import setup_logging
from app.models import User

logger = setup_logging()
revoked_store = set()


@jwt.token_in_blocklist_loader
def check_if_token_in_blocklist(header, jwt_payload):
    return jwt_payload["jti"] in revoked_store


def get_user_from_jwt():
    try:
        logger.info("Fetching user from JWT.")
        return User.query.get(get_jwt_identity())
    except Exception as e:
        logger.error(f"Unexpected error during logout: {e}", exc_info=True)
        return None


def get_user_id_from_jwt():
    identity = get_jwt_identity()
    try:
        user_id = int(identity)
        return user_id
    except (TypeError, ValueError):
        logger.error(f"Invalid user ID format in JWT: {identity}")
        return None
