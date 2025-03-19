import logging
from typing import List, Optional

from sqlalchemy.exc import SQLAlchemyError

from app.models.user import User, db


def get_users() -> List[User]:
    return User.query.all()


def get_user_by_id(user_id: int) -> Optional[User]:
    return User.query.get(user_id)



def add_user(username: str, password: str, first_name: str, last_name: str, email: str,
             date_of_birth: Optional[str] = None, description: Optional[str] = None) -> Optional[User]:
    try:
        if User.query.filter_by(email=email).first():
            logging.basicConfig(level=logging.DEBUG,
                                format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')
            logging.error(f'User with email {email} already exists')
            return None

        if User.query.filter_by(username=username).first():
            logging.error(f'User with username {username} already exists')
            return None

        user = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
        )
        user.hash_password(password)
        if date_of_birth:
            user.date_of_birth = date_of_birth
        if description:
            user.description = description
        db.session.add(user)
        db.session.commit()
        return user
    except SQLAlchemyError as e:
        db.session.rollback()
        logging.error(f"Error adding user: {e}")
        return None


def update_user(user_id: int, **kwargs) -> Optional[User]:
    user = get_user_by_id(user_id)
    if not user:
        return None
    try:
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        db.session.commit()
        return user
    except SQLAlchemyError as e:
        db.session.rollback()
        logging.error(f"Error updating user: {e}")
        return None


def delete_user(user_id: int) -> bool:
    user = get_user_by_id(user_id)
    if not user:
        return False
    try:
        db.session.delete(user)
        db.session.commit()
        return True
    except SQLAlchemyError as e:
        db.session.rollback()
        logging.error(f"Error deleting user: {e}")
        return False
