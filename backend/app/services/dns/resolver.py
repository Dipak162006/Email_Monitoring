from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import List, Optional

import dns.exception
import dns.resolver

from app.modules.domains.models import DomainVerificationStatus
from app.services.dns.exceptions import (
    DNSDomainNotFoundError,
    DNSNoAnswerError,
    DNSResolutionError,
    DNSTemporaryError,
    DNSTimeoutError,
)

logger = logging.getLogger(__name__)


@dataclass
class DNSVerificationResult:
    """Structured result of domain DNS checks."""
    mx_status: str
    spf_status: str
    dkim_status: str
    dmarc_status: str
    verification_status: str
    verification_error: Optional[str]
    last_checked_at: datetime


class DNSResolver:
    """Low-level DNS resolver wrapper using dnspython with strict timeouts."""

    def __init__(self, timeout: float = 3.0, lifetime: float = 3.0):
        self.timeout = timeout
        self.lifetime = lifetime
        self._resolver = dns.resolver.Resolver()
        self._resolver.timeout = timeout
        self._resolver.lifetime = lifetime

    def resolve_mx(self, domain: str) -> List[str]:
        """Query MX records for a domain.
        
        Returns list of exchange hostnames.
        Returns empty list if no MX records exist (NoAnswer).
        """
        try:
            answers = self._resolver.resolve(domain, "MX")
            return [str(rdata.exchange).rstrip(".") for rdata in answers]
        except dns.resolver.NXDOMAIN:
            raise DNSDomainNotFoundError(f"Domain '{domain}' does not exist in DNS")
        except dns.resolver.NoAnswer:
            return []
        except (dns.resolver.Timeout, dns.exception.Timeout):
            raise DNSTimeoutError(f"DNS query timed out for '{domain}'")
        except dns.resolver.NoNameservers:
            raise DNSTemporaryError(f"No nameservers responded for '{domain}'")
        except dns.exception.DNSException as e:
            raise DNSResolutionError(f"DNS resolution error for '{domain}': {str(e)}")

    def resolve_txt(self, query_name: str) -> List[str]:
        """Query TXT records for a hostname, properly concatenating multi-string chunks.
        
        Returns list of joined TXT record contents.
        Returns empty list if no TXT records exist (NoAnswer).
        """
        try:
            answers = self._resolver.resolve(query_name, "TXT")
            records: List[str] = []
            for rdata in answers:
                if hasattr(rdata, "strings"):
                    chunk_strs = [
                        s.decode("utf-8", errors="replace") if isinstance(s, bytes) else str(s)
                        for s in rdata.strings
                    ]
                    records.append("".join(chunk_strs))
                else:
                    records.append(rdata.to_text().strip('"'))
            return records
        except dns.resolver.NXDOMAIN:
            raise DNSDomainNotFoundError(f"Domain '{query_name}' does not exist in DNS")
        except dns.resolver.NoAnswer:
            return []
        except (dns.resolver.Timeout, dns.exception.Timeout):
            raise DNSTimeoutError(f"DNS query timed out for '{query_name}'")
        except dns.resolver.NoNameservers:
            raise DNSTemporaryError(f"No nameservers responded for '{query_name}'")
        except dns.exception.DNSException as e:
            raise DNSResolutionError(f"DNS resolution error for '{query_name}': {str(e)}")


def verify_domain_dns(
    domain_name: str,
    dkim_selector: Optional[str] = None,
    resolver: Optional[DNSResolver] = None,
) -> DNSVerificationResult:
    """Perform synchronous DNS checks for MX, SPF, DKIM, and DMARC on a domain.
    
    Applies deterministic status calculation and safe human-readable error summaries.
    """
    if resolver is None:
        resolver = DNSResolver()

    now = datetime.now(timezone.utc)
    errors: List[str] = []

    # 1. MX Verification
    try:
        mx_records = resolver.resolve_mx(domain_name)
        if mx_records:
            mx_status = DomainVerificationStatus.VERIFIED.value
        else:
            mx_status = DomainVerificationStatus.FAILED.value
            errors.append("MX record not found")
    except DNSDomainNotFoundError:
        return DNSVerificationResult(
            mx_status=DomainVerificationStatus.FAILED.value,
            spf_status=DomainVerificationStatus.FAILED.value,
            dkim_status=DomainVerificationStatus.FAILED.value if dkim_selector else DomainVerificationStatus.PENDING.value,
            dmarc_status=DomainVerificationStatus.FAILED.value,
            verification_status=DomainVerificationStatus.FAILED.value,
            verification_error="DNS lookup failed: domain does not exist.",
            last_checked_at=now,
        )
    except DNSTimeoutError:
        return DNSVerificationResult(
            mx_status=DomainVerificationStatus.FAILED.value,
            spf_status=DomainVerificationStatus.FAILED.value,
            dkim_status=DomainVerificationStatus.FAILED.value if dkim_selector else DomainVerificationStatus.PENDING.value,
            dmarc_status=DomainVerificationStatus.FAILED.value,
            verification_status=DomainVerificationStatus.FAILED.value,
            verification_error="DNS resolution timed out.",
            last_checked_at=now,
        )
    except DNSTemporaryError:
        return DNSVerificationResult(
            mx_status=DomainVerificationStatus.FAILED.value,
            spf_status=DomainVerificationStatus.FAILED.value,
            dkim_status=DomainVerificationStatus.FAILED.value if dkim_selector else DomainVerificationStatus.PENDING.value,
            dmarc_status=DomainVerificationStatus.FAILED.value,
            verification_status=DomainVerificationStatus.FAILED.value,
            verification_error="Temporary DNS resolution error.",
            last_checked_at=now,
        )
    except Exception:
        logger.exception("Unexpected DNS resolution error during MX check for %s", domain_name)
        return DNSVerificationResult(
            mx_status=DomainVerificationStatus.FAILED.value,
            spf_status=DomainVerificationStatus.FAILED.value,
            dkim_status=DomainVerificationStatus.FAILED.value if dkim_selector else DomainVerificationStatus.PENDING.value,
            dmarc_status=DomainVerificationStatus.FAILED.value,
            verification_status=DomainVerificationStatus.FAILED.value,
            verification_error="Unexpected DNS resolution failure.",
            last_checked_at=now,
        )

    # 2. SPF Verification (Query TXT on domain)
    try:
        txt_records = resolver.resolve_txt(domain_name)
        spf_records = [r for r in txt_records if r.strip().lower().startswith("v=spf1")]
        if spf_records:
            spf_status = DomainVerificationStatus.VERIFIED.value
        else:
            spf_status = DomainVerificationStatus.FAILED.value
            errors.append("SPF record not found")
    except DNSDomainNotFoundError:
        spf_status = DomainVerificationStatus.FAILED.value
        errors.append("SPF lookup failed: domain does not exist")
    except (DNSTimeoutError, DNSTemporaryError, DNSResolutionError, Exception) as e:
        logger.warning("DNS error during SPF check for %s: %s", domain_name, str(e))
        spf_status = DomainVerificationStatus.FAILED.value
        errors.append("SPF DNS lookup failed")

    # 3. DKIM Verification
    if not dkim_selector or not dkim_selector.strip():
        dkim_status = DomainVerificationStatus.PENDING.value
        errors.append("DKIM verification skipped: no selector configured.")
    else:
        dkim_query_name = f"{dkim_selector.strip()}._domainkey.{domain_name}"
        try:
            dkim_txt_records = resolver.resolve_txt(dkim_query_name)
            # Recognize record containing v=DKIM1 or public key declaration p=
            dkim_valid = [
                r for r in dkim_txt_records
                if "v=dkim1" in r.lower() or "p=" in r.lower()
            ]
            if dkim_valid:
                dkim_status = DomainVerificationStatus.VERIFIED.value
            else:
                dkim_status = DomainVerificationStatus.FAILED.value
                errors.append(f"DKIM record not found for selector '{dkim_selector}'")
        except (DNSDomainNotFoundError, DNSNoAnswerError):
            dkim_status = DomainVerificationStatus.FAILED.value
            errors.append(f"DKIM record not found for selector '{dkim_selector}'")
        except (DNSTimeoutError, DNSTemporaryError, DNSResolutionError, Exception) as e:
            logger.warning("DNS error during DKIM check for %s: %s", dkim_query_name, str(e))
            dkim_status = DomainVerificationStatus.FAILED.value
            errors.append(f"DKIM DNS lookup failed for selector '{dkim_selector}'")

    # 4. DMARC Verification (Query TXT on _dmarc.<domain>)
    dmarc_query_name = f"_dmarc.{domain_name}"
    try:
        dmarc_txt_records = resolver.resolve_txt(dmarc_query_name)
        dmarc_records = [r for r in dmarc_txt_records if r.strip().lower().startswith("v=dmarc1")]
        if not dmarc_records:
            dmarc_status = DomainVerificationStatus.FAILED.value
            errors.append("DMARC record not found")
        else:
            # Check policy p=
            record_str = dmarc_records[0]
            policy = None
            for part in record_str.split(";"):
                part_clean = part.strip().lower()
                if part_clean.startswith("p="):
                    policy = part_clean.split("=", 1)[1].strip()
                    break

            if policy == "none":
                dmarc_status = DomainVerificationStatus.WARNING.value
                errors.append("DMARC policy is set to p=none (warning)")
            elif policy in ("quarantine", "reject"):
                dmarc_status = DomainVerificationStatus.VERIFIED.value
            else:
                dmarc_status = DomainVerificationStatus.WARNING.value
                errors.append(f"DMARC policy '{policy}' evaluated as warning")
    except (DNSDomainNotFoundError, DNSNoAnswerError):
        dmarc_status = DomainVerificationStatus.FAILED.value
        errors.append("DMARC record not found")
    except (DNSTimeoutError, DNSTemporaryError, DNSResolutionError, Exception) as e:
        logger.warning("DNS error during DMARC check for %s: %s", dmarc_query_name, str(e))
        dmarc_status = DomainVerificationStatus.FAILED.value
        errors.append("DMARC DNS lookup failed")

    # 5. Overall Status Calculation
    if mx_status == DomainVerificationStatus.FAILED.value or spf_status == DomainVerificationStatus.FAILED.value:
        overall_status = DomainVerificationStatus.FAILED.value
    elif dkim_status == DomainVerificationStatus.VERIFIED.value and dmarc_status == DomainVerificationStatus.VERIFIED.value:
        overall_status = DomainVerificationStatus.VERIFIED.value
    else:
        # Hard requirements (MX, SPF) passed, but DKIM or DMARC has warning/pending/failure
        overall_status = DomainVerificationStatus.WARNING.value

    # Build human-readable error summary
    if overall_status == DomainVerificationStatus.VERIFIED.value:
        summary_error = None
    else:
        summary_error = "; ".join(errors) if errors else None
        if summary_error and len(summary_error) > 500:
            summary_error = summary_error[:497] + "..."

    return DNSVerificationResult(
        mx_status=mx_status,
        spf_status=spf_status,
        dkim_status=dkim_status,
        dmarc_status=dmarc_status,
        verification_status=overall_status,
        verification_error=summary_error,
        last_checked_at=now,
    )
