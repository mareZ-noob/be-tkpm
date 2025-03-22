import datetime
import os

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS
from flask_migrate import Migrate

from app.models import db
from app.routes import register_routes
from app.utils.jwt_helpers import jwt

# Load environment variables from .env file
load_dotenv()


def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
    )
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'secret')

    if os.getenv('FLASK_ENV') == 'production':
        app.config['DEBUG'] = False
        app.config['SQLALCHEMY_ECHO'] = False
    else:
        app.config['DEBUG'] = True
        app.config['SQLALCHEMY_ECHO'] = True

    # JWT Configuration
    app.config['JWT_SECRET_KEY'] = os.getenv('SECRET_KEY', 'secret')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = datetime.timedelta(minutes=15)
    app.config['JWT_REFRESH_TOKEN_EXPIRES'] = datetime.timedelta(days=30)
    app.config['JWT_TOKEN_LOCATION'] = ['cookies', 'headers']
    app.config['JWT_COOKIE_SECURE'] = False  # Use True in production with HTTPS
    app.config['JWT_COOKIE_SAMESITE'] = 'Strict'
    app.config['JWT_REFRESH_COOKIE_PATH'] = '/'
    app.config['JWT_COOKIE_CSRF_PROTECT'] = False

    app.config['FLASK_RUN_HOST'] = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    app.config['FLASK_RUN_PORT'] = int(os.getenv("FLASK_RUN_PORT", 5000))

    # Initialize SQLAlchemy
    db.init_app(app)

    # Initialize JWT
    jwt.init_app(app)

    # Initialize Migrate
    migrate = Migrate(app, db)
    migrate.init_app(app, db)

    # Register all routes
    register_routes(app)

    # Allow for CORS requests from the frontend server
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

    return app
