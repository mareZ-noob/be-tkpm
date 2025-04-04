from flask import Blueprint

from app.controllers.create_controllers import get_wiki_summary

create_bp = Blueprint('create', __name__, url_prefix='/create')

create_bp.route('/prompt', methods=['POST'])(get_wiki_summary)
# create_bp.route('/text', methods=['POST'])()
# create_bp.route('/refresh', methods=['POST'])()
# create_bp.route('/logout', methods=['POST'])()
