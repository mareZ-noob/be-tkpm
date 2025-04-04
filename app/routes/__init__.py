from app.routes.auth_routes import auth_bp
from app.routes.create_routes import create_bp
from app.routes.document_routes import doc_bp
from app.routes.test_routes import test_bp
from app.routes.tts_routes import tts_bp
from app.routes.user_routes import user_bp


def register_routes(app):
    app.register_blueprint(user_bp)
    app.register_blueprint(test_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(doc_bp)
    app.register_blueprint(create_bp)
    app.register_blueprint(tts_bp)
