from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

from app.models import db


class Resource(db.Model):
    __tablename__ = 'resources'

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, ForeignKey('users.id'), nullable=False)

    user = relationship('User', back_populates='resources')

    def __init__(self, url, user_id):
        self.url = url
        self.user_id = user_id

    def __repr__(self):
        return f'<Resource ID: {self.id}, URL: {self.url}, User ID: {self.user_id}>'
