from app.config.extensions import jwt

revoked_store = set()


@jwt.token_in_blocklist_loader
def check_if_token_in_blocklist(jwt_payload):
    return jwt_payload["jti"] in revoked_store
