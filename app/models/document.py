from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import relationship

from app.config.extensions import db


class Document(db.Model):
    __tablename__ = 'documents'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(255), nullable=True)
    content = db.Column(db.Text)
    starred = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now(), default=func.now())

    user = relationship('User', back_populates='documents')

    def __init__(self, user_id, content, title=None):
        self.user_id = user_id
        self.content = content
        self.title = title

    def __repr__(self):
        return f'<ID: {self.id}, User ID: {self.user_id}, Title: {self.title}>, Content: {self.content}>'

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'content': self.content,
            'starred': self.starred,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def from_dict(self, data):
        for field in ['user_id', 'content', 'title', 'starred']:
            if field in data:
                setattr(self, field, data[field])
        return self
