from flask import Blueprint

from app.controllers.agent_controller import get_all_models, get_models_by_provider, get_provider, get_script

agent_bp = Blueprint('agent', __name__, url_prefix='/agents')

agent_bp.route('/', methods=['GET'])(get_all_models)
agent_bp.route('/provider', methods=['GET'])(get_provider)
agent_bp.route('/<provider>', methods=['GET'])(get_models_by_provider)
agent_bp.route('/generate-script', methods=['POST'])(get_script)
