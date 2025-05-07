from flask import jsonify, request
from flask_jwt_extended import jwt_required

from app.config.extensions import db
from app.config.logging_config import setup_logging
from app.models import Document
from app.utils.exceptions import MissingParameterException, ResourceNotFoundException
from app.utils.jwt_helpers import get_user_from_jwt, get_user_id_from_jwt

logger = setup_logging()


@jwt_required()
def create_document():
    data = request.get_json()
    user_id = get_user_id_from_jwt()
    if user_id is None:
        logger.error("Create document failed: User ID not provided.")
        raise MissingParameterException("Missing required fields: user_id")

    title = data.get('title')
    content = data.get('content')

    if not content:
        logger.error("Create document failed: Missing content.")
        raise MissingParameterException("Missing required fields: content")

    if not title:
        words = content.split()
        title = ' '.join(words[:10]) + ('...' if len(words) > 10 else '')
        logger.info(f"Create document title: {title}")

    new_doc = Document(user_id=user_id, content=content, title=title)
    db.session.add(new_doc)
    db.session.commit()

    logger.info(f"Document created: {new_doc}")
    return jsonify(new_doc.to_dict()), 201


@jwt_required()
def update_document(document_id):
    document = Document.query.get(document_id)
    if not document:
        logger.error("Update document failed: Document not found.")
        raise ResourceNotFoundException("Document not found")

    data = request.get_json()
    document.from_dict(data)
    db.session.commit()

    logger.info(f"Update document: {document_id}")
    return jsonify(document.to_dict())


@jwt_required()
def delete_document(document_id):
    document = Document.query.get(document_id)
    if not document:
        logger.error("Delete document failed: Document not found.")
        raise ResourceNotFoundException("Document not found")

    db.session.delete(document)
    db.session.commit()

    logger.info(f"Delete document {document_id}")
    return jsonify({"msg": "Document deleted"}), 200


@jwt_required()
def get_user_documents():
    user = get_user_from_jwt()
    if user is None:
        logger.error("Get user documents failed: User not found.")
        raise ResourceNotFoundException("User not found")
    documents = Document.query.filter_by(user_id=user.id).all()
    logger.info(f"User {user.id} has {len(documents)} documents.")
    return jsonify([doc.to_dict() for doc in documents])


@jwt_required()
def search_documents():
    user = get_user_from_jwt()
    if user is None:
        logger.error("Search documents failed: User not found.")
        raise ResourceNotFoundException("User not found")

    search_query = request.args.get('query')
    if not search_query:
        documents = Document.query.filter_by(user_id=user.id).all()
        return jsonify([doc.to_dict() for doc in documents])

    documents = Document.query.filter(
        Document.user_id == user.id,
        Document.content.ilike(f"%{search_query}%")
    ).all()

    return jsonify([doc.to_dict() for doc in documents])


@jwt_required()
def duplicate_document(document_id):
    document = Document.query.get(document_id)
    if not document:
        logger.error("Duplicate document failed: Document not found.")
        raise ResourceNotFoundException("Document not found")

    data = request.get_json()
    title = data.get('title', 'Untitled')

    new_document = Document(
        user_id=document.user_id,
        content=document.content,
        title=title,
        starred=document.starred
    )
    db.session.add(new_document)
    db.session.commit()

    logger.info(f"Duplicate document: {document_id}")
    return jsonify(new_document.to_dict()), 201
