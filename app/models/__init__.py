from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from .resource import Resource
from .user import User
from .document import Document
