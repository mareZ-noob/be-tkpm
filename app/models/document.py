from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import relationship

from app.config.extensions import db


# Define a Document model
class Document(db.Model):
    __tablename__ = 'documents'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, ForeignKey('users.id'), nullable=False)
    text = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now(), default=func.now())

    user = relationship('User', back_populates='documents')

    def __init__(self, user_id, text):
        self.userId = user_id
        self.text = text

    def __repr__(self):
        return f'<ID: {self.id}, User ID: {self.user_id}, Text: {self.text}>'

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'text': self.text,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def from_dict(self, data):
        for field in ['user_id', 'text']:
            if field in data:
                setattr(self, field, data[field])
        return self
