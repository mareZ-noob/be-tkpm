from flask import jsonify, request

from app.config.logging_config import setup_logging
from app.crawl.crawler import generate_youtube_script

logger = setup_logging()


# @jwt_required()
def get_youtube_script():
    try:
        data = request.get_json()

        required_fields = ['keyword', 'style', 'age', 'language', 'tone']
        missing_fields = [field for field in required_fields if not data.get(field)]

        if missing_fields:
            return jsonify({"msg": f"Missing fields: {', '.join(missing_fields)}"}), 400

        script = generate_youtube_script(data)
        logger.info(f"Generated script: {script}")
        return jsonify({"summary": script}), 200

    except Exception as e:
        return jsonify({"msg": "Internal server error", "error": str(e)}), 500
