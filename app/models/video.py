from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import relationship

from app.config.extensions import db


class Video(db.Model):
    __tablename__ = 'videos'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(255), nullable=True)
    url = db.Column(db.String(255), nullable=False)
    starred = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now(), default=func.now())

    user = relationship('User', back_populates='videos')

    def __init__(self, user_id, url, title=None):
        self.userId = user_id
        self.url = url
        self.title = title

    def __repr__(self):
        return f'<ID: {self.id}, User ID: {self.user_id}, Title: {self.title}>, URL: {self.url}>'

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'url': self.url,
            'starred': self.starred,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def from_dict(self, data):
        for field in ['user_id', 'url', 'title', 'starred']:
            if field in data:
                setattr(self, field, data[field])
        return self
