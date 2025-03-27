from flask_jwt_extended import JWTManager

# Store revoked tokens in memory (Maybe use Redis or Database in production)
revoked_store = set()

jwt = JWTManager()


@jwt.token_in_blocklist_loader
def check_if_token_in_blocklist(jwt_header, jwt_payload):
    return jwt_payload["jti"] in revoked_store  # Kiểm tra token có bị block không
