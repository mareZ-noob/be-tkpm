
from flask import jsonify, request
from app.models.document import Document, db


def create_document():
    data = request.get_json()
    user_id = data.get('userId')
    text = data.get('text')

    if not user_id or not text:
        return jsonify({"error": "Missing userId or text"}), 400

    new_doc = Document(userId=user_id, text=text)
    db.session.add(new_doc)
    db.session.commit()

    return jsonify(new_doc.to_dict()), 201

def update_document(document_id):
    document = Document.query.get(document_id)
    if not document:
        return jsonify({"error": "Document not found"}), 404

    data = request.get_json()
    document.from_dict(data)
    db.session.commit()

    return jsonify(document.to_dict())

def delete_document(document_id):
    document = Document.query.get(document_id)
    if not document:
        return jsonify({"error": "Document not found"}), 404

    db.session.delete(document)
    db.session.commit()

    return jsonify({"message": "Document deleted"}), 200

def get_user_documents(user_id):
    documents = Document.query.filter_by(userId=user_id).all()
    return jsonify([doc.to_dict() for doc in documents])