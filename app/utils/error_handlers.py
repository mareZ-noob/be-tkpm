from flask import jsonify

from app.utils.exceptions import (
    BadRequestException,
    EmailAlreadyExistsException,
    ForbiddenException,
    InternalServerException,
    InvalidCredentialsException,
    InvalidEmailException,
    InvalidPasswordException,
    InvalidTokenException,
    InvalidUsernameException,
    MissingParameterException,
    PasswordResetLimitExceededException,
    ResourceNotFoundException,
    ServiceUnavailableException,
    TokenExpiredException,
    TokenRevokedException,
    UnauthorizedException,
    UserAlreadyExistsException,
    UsernameAlreadyExistsException,
)


def register_error_handlers(app):
    # Default error handlers
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({
            'error': str(error),
            'msg': 'Bad Request',
        }), 400

    @app.errorhandler(401)
    def unauthorized(error):
        return jsonify({
            'error': str(error),
            'msg': 'Authentication required',
        }), 401

    @app.errorhandler(403)
    def forbidden(error):
        return jsonify({
            'error': str(error),
            'msg': 'Access denied',
        }), 403

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'error': str(error),
            'msg': 'Resource not found',
        }), 404

    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        return jsonify({
            'error': str(error),
            'msg': 'Rate limit exceeded. You can only request 5 password resets per hour.',
        }), 429

    @app.errorhandler(500)
    def internal_server_error(error):
        return jsonify({
            'error': str(error),
            'msg': 'An unexpected error occurred. Please try again later',
        }), 500

    @app.errorhandler(Exception)
    def handle_uncaught_exception(error):
        return jsonify({
            'error': str(error),
            'msg': 'An unexpected error occurred.',
        }), 500

    # Custom error handlers for specific exceptions
    error_map = {
        ResourceNotFoundException: ("Resource not found", 404),
        InvalidCredentialsException: ("Invalid credentials", 401),
        UserAlreadyExistsException: ("User already exists", 400),
        InvalidTokenException: ("Invalid token", 401),
        TokenExpiredException: ("Token has expired", 401),
        TokenRevokedException: ("Token has been revoked", 401),
        PasswordResetLimitExceededException: ("Password reset limit exceeded", 429),
        InvalidPasswordException: ("Invalid password", 400),
        InvalidEmailException: ("Invalid email", 400),
        InvalidUsernameException: ("Invalid username", 400),
        EmailAlreadyExistsException: ("Email already exists", 400),
        UsernameAlreadyExistsException: ("Username already exists", 400),
        InternalServerException: ("Internal server error", 500),
        ForbiddenException: ("Access denied", 403),
        BadRequestException: ("Bad request", 400),
        UnauthorizedException: ("Authentication required", 401),
        MissingParameterException: ("Missing parameter", 400),
        ServiceUnavailableException: ("Service unavailable", 503),
    }

    for exception, (message, status_code) in error_map.items():
        @app.errorhandler(exception)
        def handle_error(message=message, status_code=status_code):
            response = jsonify({"msg": str(message)})
            response.status_code = status_code
            return response
