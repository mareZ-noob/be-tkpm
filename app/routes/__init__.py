from app.routes.test_routes import test_bp
from app.routes.user_routes import user_bp
from app.routes.auth_routes import auth_bp



def register_routes(app):
    app.register_blueprint(user_bp)
    app.register_blueprint(test_bp)
    app.register_blueprint(auth_bp)
