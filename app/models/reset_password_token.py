import hashlib
import secrets
import string
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import relationship

from app.config.extensions import db


class ResetPasswordToken(db.Model):
    __tablename__ = 'reset_password_tokens'

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(256), nullable=False, unique=True)
    user_id = db.Column(db.Integer, ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now(), default=func.now())
    expired_at = db.Column(db.DateTime(timezone=True), nullable=False)

    user = relationship('User', back_populates='reset_password_tokens')

    def __init__(self, token, user_id):
        self.token = token
        self.user_id = user_id
        self.expired_at = datetime.now(timezone.utc) + timedelta(hours=1)

    def __repr__(self):
        return f'<ID: {self.id}, Token: {self.token}, User ID: {self.user_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'token': self.token,
            'user_id': self.user_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'expired_at': self.expired_at
        }

    @staticmethod
    def create_reset_password_token(user_id):
        characters = string.ascii_letters + string.digits
        random_token_part = ''.join(secrets.choice(characters) for _ in range(64))

        user_id_hash = hashlib.sha256(str(user_id).encode('utf-8')).hexdigest()

        token = str(uuid4()) + '-' + user_id_hash + '-' + random_token_part

        return token
