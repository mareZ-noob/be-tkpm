from flask import Blueprint

from app.controllers.document_controller import (
    create_document,
    delete_document,
    duplicate_document,
    get_user_documents,
    update_document,
)

doc_bp = Blueprint('document', __name__, url_prefix='/documents')

doc_bp.route('/', methods=['POST'])(create_document)
doc_bp.route('/', methods=['GET'])(get_user_documents)
doc_bp.route('/<int:document_id>', methods=['PUT'])(update_document)
doc_bp.route('/<int:document_id>', methods=['DELETE'])(delete_document)
doc_bp.route('/<int:document_id>/duplicate', methods=['POST'])(duplicate_document)
