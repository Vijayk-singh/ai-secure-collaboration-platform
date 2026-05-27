from fastapi import HTTPException, status

class CredentialException(HTTPException):
    """
    Exception thrown when token parsing, signature validation, or decryption fails.
    """
    def __init__(self, detail: str = "Could not validate credentials") -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

class InvalidCredentialsException(HTTPException):
    """
    Exception thrown during login when email or password doesn't match.
    """
    def __init__(self, detail: str = "Incorrect email or password") -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

class InactiveUserException(HTTPException):
    """
    Exception thrown when a locked or disabled user attempts to perform requests.
    """
    def __init__(self, detail: str = "Inactive user account") -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )

class EmailExistsException(HTTPException):
    """
    Exception thrown when a user registers with an email that is already in use.
    """
    def __init__(self, detail: str = "A user with this email address already exists") -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )

class InsufficientPermissionsException(HTTPException):
    """
    Exception thrown during RBAC checks when a user doesn't possess the required role.
    """
    def __init__(self, detail: str = "Insufficient permissions to access this resource") -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )
