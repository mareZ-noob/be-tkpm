from flask import Blueprint, jsonify

test_bp = Blueprint('test', __name__, url_prefix='/')


@test_bp.route('/', methods=['GET'])
def hello():
    return jsonify({"message": "Hello, world!"})
