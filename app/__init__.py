import os

from dotenv import load_dotenv
from flask import Flask

from app.config.extensions import celery, cors, db, jwt, limiter, mail, migrate
from app.config.settings import config
from app.routes import register_routes
from app.utils.error_handlers import register_error_handlers
from app.utils.request_handlers import cleanup_tts_files

load_dotenv()


def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'default')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Check required environment variables
    if os.getenv('GEMINI_API_KEY') is None or os.getenv('GEMINI_API_KEY') == "":
        raise ValueError("GEMINI_API_KEY is not set")

    if os.getenv('MAIL_USERNAME') is None or os.getenv('MAIL_USERNAME') == "":
        raise ValueError("MAIL_USERNAME is not set")

    if os.getenv('MAIL_PASSWORD') is None or os.getenv('MAIL_PASSWORD') == "":
        raise ValueError("MAIL_PASSWORD is not set")

    # Initialize SQLAlchemy
    db.init_app(app)

    # Initialize Celery
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask

    # Initialize JWT
    jwt.init_app(app)

    # Initialize Limiter
    limiter.init_app(app)

    # Initialize Migrate
    migrate.init_app(app, db)

    # Initialize Mail
    mail.init_app(app)

    # Register all routes
    register_routes(app)

    # Register the after_request handler
    app.after_request(cleanup_tts_files)

    # Register error handlers
    register_error_handlers(app)

    # Allow for CORS requests from the frontend server
    cors.init_app(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

    return app
