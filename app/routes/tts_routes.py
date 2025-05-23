from flask import Blueprint

from app.controllers.tts_controller import (
    concatenate_and_upload,
    filter_voices,
    generate_tts,
    get_list_engines,
    get_list_languages,
)

tts_bp = Blueprint('tts', __name__, url_prefix='/tts')

tts_bp.route('/engines', methods=['GET'])(get_list_engines)
tts_bp.route('/languages', methods=['POST'])(get_list_languages)
tts_bp.route('/voices/filter', methods=['POST'])(filter_voices)
tts_bp.route('/generate', methods=['POST'])(generate_tts)
tts_bp.route('/concatenate-and-upload', methods=['POST'])(concatenate_and_upload)
