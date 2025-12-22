class AntigravityError(Exception):
    """Base exception for the application."""
    pass

class APIError(AntigravityError):
    """Exception raised for API related errors."""
    def __init__(self, message: str, code: int, status_code: int):
        super().__init__(f"[{code}] {message} (HTTP {status_code})")
        self.code = code
        self.status_code = status_code
