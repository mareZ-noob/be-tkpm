from sqlalchemy import func
from sqlalchemy.orm import relationship
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import db


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    gender = db.Column(db.String(100), unique=False, nullable=True)
    date_of_birth = db.Column(db.Date)
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now(), default=func.now())
    is_active = db.Column(db.Boolean, default=True)

    resources = relationship('Resource', back_populates='user')

    def __init__(self, username, email, password, first_name=None, last_name=None, date_of_birth=None,
                 description=None):
        self.username = username
        self.password = password
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.description = description
        self.date_of_birth = date_of_birth

    def __repr__(self):
        return f'<ID: {self.id}, Username: {self.username}, Email: {self.email}>'

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'email': self.email,
            'description': self.description,
            'date_of_birth': self.date_of_birth,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def from_dict(self, data):
        for field in ['username', 'password', 'first_name', 'last_name', 'email', 'description', 'date_of_birth']:
            if field in data:
                setattr(self, field, data[field])
        return self

    def hash_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)
