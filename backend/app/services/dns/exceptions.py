class DNSException(Exception):
    """Base exception for all domain DNS resolution errors."""
    def __init__(self, message: str = "DNS resolution error"):
        super().__init__(message)
        self.message = message


class DNSDomainNotFoundError(DNSException):
    """Raised when the domain does not exist in DNS (NXDOMAIN)."""
    def __init__(self, message: str = "Domain does not exist in DNS"):
        super().__init__(message)


class DNSTimeoutError(DNSException):
    """Raised when DNS resolution times out."""
    def __init__(self, message: str = "DNS resolution timed out"):
        super().__init__(message)


class DNSNoAnswerError(DNSException):
    """Raised when a specific record type does not exist for the domain."""
    def __init__(self, message: str = "No answer returned for record query"):
        super().__init__(message)


class DNSTemporaryError(DNSException):
    """Raised when a temporary network or nameserver error occurs."""
    def __init__(self, message: str = "Temporary DNS resolution error"):
        super().__init__(message)


class DNSResolutionError(DNSException):
    """Raised when an unexpected or malformed DNS response occurs."""
    def __init__(self, message: str = "Malformed or unexpected DNS response"):
        super().__init__(message)
