from flask import Blueprint

from app.controllers.create_controllers import get_youtube_script
from app.controllers.document_controller import create_document

create_bp = Blueprint('create', __name__, url_prefix='/create')

create_bp.route('/prompt', methods=['POST'])(get_youtube_script)
create_bp.route('/text', methods=['POST'])(create_document)
# create_bp.route('/refresh', methods=['POST'])()
# create_bp.route('/logout', methods=['POST'])()
