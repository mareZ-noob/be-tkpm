from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.config.extensions import db
from app.models.document import Document


@jwt_required()
def create_document():
    data = request.get_json()
    current_user = get_jwt_identity()
    text = data.get('text')

    if not current_user or not text:
        return jsonify({"msg": "Missing userId or text"}), 400

    new_doc = Document(user_id=current_user, text=text)
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


@jwt_required
def delete_document(document_id):
    document = Document.query.get(document_id)
    if not document:
        return jsonify({"msg": "Document not found"}), 404

    db.session.delete(document)
    db.session.commit()

    return jsonify({"msg": "Document deleted"}), 200


@jwt_required()
def get_user_documents(user_id):
    documents = Document.query.filter_by(user_id=user_id).all()
    return jsonify([doc.to_dict() for doc in documents])
