from flask_jwt_extended import JWTManager

# Store revoked tokens in memory (Maybe use Redis or Database in production)
revoked_store = set()

jwt = JWTManager()


# Token blocklist checking function
@jwt.token_in_blocklist_loader
def check_if_token_in_blocklist(jwt_payload):
    jti = jwt_payload["jti"]
    return jti in revoked_store
