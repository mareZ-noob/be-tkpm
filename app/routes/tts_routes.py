from flask import Blueprint

from app.controllers.tts_controller import filter_voices, generate_tts, get_list_languages, get_list_engines

tts_bp = Blueprint('tts', __name__, url_prefix='/tts')

tts_bp.route('/engines', methods=['GET'])(get_list_engines)
tts_bp.route('/languages', methods=['POST'])(get_list_languages)
tts_bp.route('/voices/filter', methods=['POST'])(filter_voices)
tts_bp.route('/generate', methods=['POST'])(generate_tts)
