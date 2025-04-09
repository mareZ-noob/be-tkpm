class ResourceFoundException(Exception):
    pass


class InvalidCredentialsException(Exception):
    pass


class UserAlreadyExistsException(Exception):
    pass


class InvalidTokenException(Exception):
    pass


class TokenExpiredException(Exception):
    pass


class TokenRevokedException(Exception):
    pass


class PasswordResetLimitExceededException(Exception):
    pass


class InvalidPasswordException(Exception):
    pass


class InvalidEmailException(Exception):
    pass


class InvalidUsernameException(Exception):
    pass


class EmailAlreadyExistsException(Exception):
    pass


class UsernameAlreadyExistsException(Exception):
    pass


class InternalServerErrorException(Exception):
    pass


class ForbiddenException(Exception):
    pass


class BadRequestException(Exception):
    pass


class UnauthorizedException(Exception):
    pass


class MissingParameterException(Exception):
    pass
