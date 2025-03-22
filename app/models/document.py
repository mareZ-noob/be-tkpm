from sqlalchemy import func
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

from app.models import db


class Document(db.Model):
    __tablename__ = 'documents'

    id = db.Column(db.Integer, primary_key=True)
    userId = db.Column(db.Integer, ForeignKey('users.id'), nullable=False)
    text = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now(), default=func.now())

    user = relationship('User', back_populates='documents')

    def __init__(self, userId, text):
        self.userId = userId
        self.text = text
        
    def __repr__(self):
        return f'<ID: {self.id}, User ID: {self.userId}, Text: {self.text}>'

    def to_dict(self):
        return {
            'id': self.id,
            'userId': self.userId,
            'text': self.text,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def from_dict(self, data):
        for field in ['userId', 'text']:
            if field in data:
                setattr(self, field, data[field])
        return self

    
