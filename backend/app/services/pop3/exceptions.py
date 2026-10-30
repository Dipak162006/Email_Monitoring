class POP3ServiceException(Exception):
    """Base exception for all POP3-related transport and protocol errors."""
    pass


class POP3AuthenticationError(POP3ServiceException):
    """Raised when authentication against the POP3 server fails (e.g. invalid credentials).
    
    This is a fatal error and must NEVER be retried automatically by worker tasks.
    """
    pass


class POP3ConnectionError(POP3ServiceException):
    """Raised when a network socket, SSL handshake, or connection timeout occurs.
    
    This is a transient error and should trigger exponential backoff retry.
    """
    pass


class POP3ConfigurationError(POP3ServiceException):
    """Raised when email account configuration is missing required POP3 parameters.
    
    This is a configuration error and must not be retried.
    """
    pass

