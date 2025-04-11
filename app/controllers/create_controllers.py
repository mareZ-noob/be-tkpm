from flask import jsonify, request
from flask_jwt_extended import jwt_required
from app.controllers.document_controller import create_document
from app.crawl.crawler import get_wikipedia_summary, generate_youtube_script


# @jwt_required()
def get_wiki_summary():
    data = request.get_json()
    keyword = data.get('keyword')

    if not keyword:
        return jsonify({"msg": "Missing keyword"}), 400

    # result = get_wikipedia_summary(keyword)

    return jsonify({"summary": "result"}), 200


# @jwt_required()
def get_youtube_script():
    try:
        data = request.get_json()

        # Kiểm tra đầy đủ các trường
        required_fields = ['keyword', 'style', 'age', 'language', 'tone']
        missing_fields = [field for field in required_fields if not data.get(field)]

        if missing_fields:
            return jsonify({"msg": f"Missing fields: {', '.join(missing_fields)}"}), 400

        # Gọi crawler để xử lý và lấy script
        script = generate_youtube_script(data)
        print("Generated script:", script)
        return jsonify({"summary": script}), 200

    except Exception as e:
        return jsonify({"msg": "Internal server error", "error": str(e)}), 500

