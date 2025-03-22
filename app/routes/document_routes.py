from flask import Blueprint
from app.controllers.document_controller import create_document, get_user_documents, update_document, delete_document

doc_bp = Blueprint('document', __name__, url_prefix='/documents')

# POST - Tạo tài liệu
doc_bp.route('/', methods=['POST'])(create_document)

# GET - Lấy danh sách tài liệu của user
doc_bp.route('/user/<int:user_id>', methods=['GET'])(get_user_documents)

# PUT - Cập nhật tài liệu
doc_bp.route('/<int:document_id>', methods=['PUT'])(update_document)

# DELETE - Xóa tài liệu
doc_bp.route('/<int:document_id>', methods=['DELETE'])(delete_document)
