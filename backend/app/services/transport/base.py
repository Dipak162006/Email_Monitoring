from abc import ABC, abstractmethod
from app.services.transport.models import EmailTransportRequest, EmailTransportResult


class EmailTransport(ABC):
    """Abstract interface defining the provider-independent email transport contract.
    
    Decouples callers (direct email sending, future campaign delivery) from concrete
    sending mechanisms (SMTP, and future specialized transports).
    """

    @abstractmethod
    async def send(self, request: EmailTransportRequest) -> EmailTransportResult:
        """Asynchronously transmit an email message according to the transport request.
        
        Args:
            request: Provider-neutral EmailTransportRequest containing sender account,
                     envelope recipients, and MIME or structured message content.
                     
        Returns:
            EmailTransportResult indicating transmission outcome and message identifier.
            
        Raises:
            EmailTransportException: On transport or delivery failure.
        """
        pass
