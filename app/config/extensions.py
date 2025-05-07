from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flask_migrate import Migrate
from flask_session import Session
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy

from app.config.celery_config import make_celery

cors = CORS()
db = SQLAlchemy()
jwt = JWTManager()
migrate = Migrate()
mail = Mail()
limiter = Limiter(get_remote_address)
celery = make_celery()
socketio = SocketIO()
session = Session()
