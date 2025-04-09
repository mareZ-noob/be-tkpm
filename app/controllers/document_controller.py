from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.config.extensions import db
from app.models import User
from app.models.document import Document


@jwt_required()
def create_document():
    data = request.get_json()
    current_user = get_jwt_identity()
    content = data.get('content')
    title = data.get('title', 'Untitled')

    if not current_user or not content:
        return jsonify({"msg": "Missing id or content"}), 400

    new_doc = Document(user_id=current_user, content=content, title=title)
    db.session.add(new_doc)
    db.session.commit()

    return jsonify(new_doc.to_dict()), 201


@jwt_required()
def update_document(document_id):
    document = Document.query.get(document_id)
    if not document:
        return jsonify({"msg": "Document not found"}), 404

    data = request.get_json()
    document.from_dict(data)
    db.session.commit()

    return jsonify(document.to_dict())


@jwt_required()
def delete_document(document_id):
    document = Document.query.get(document_id)
    if not document:
        return jsonify({"msg": "Document not found"}), 404

    db.session.delete(document)
    db.session.commit()

    return jsonify({"msg": "Document deleted"}), 200


@jwt_required()
def get_user_documents():
    current_user = get_jwt_identity()
    user = User.query.get(current_user)
    if not user:
        return jsonify({"msg": "User not found"}), 404
    documents = Document.query.filter_by(user_id=user.id).all()
    return jsonify([doc.to_dict() for doc in documents])


@jwt_required()
def search_documents():
    current_user = get_jwt_identity()
    user = User.query.get(current_user)
    if not user:
        return jsonify({"msg": "User not found"}), 404

    search_query = request.args.get('query')
    if not search_query:
        documents = Document.query.filter_by(user_id=user.id).all()
        return jsonify([doc.to_dict() for doc in documents])

    documents = Document.query.filter(
        Document.user_id == user.id,
        Document.content.ilike(f"%{search_query}%")
    ).all()

    return jsonify([doc.to_dict() for doc in documents])

