from flask import jsonify, request
from flask_jwt_extended import jwt_required

# from app.crawl.crawler import get_wikipedia_summary


# @jwt_required()
def get_wiki_summary():
    data = request.get_json()
    keyword = data.get('keyword')

    if not keyword:
        return jsonify({"msg": "Missing keyword"}), 400

    # result = get_wikipedia_summary(keyword)

    return jsonify({"summary": "result"}), 200
