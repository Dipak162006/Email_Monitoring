"""Sending Window & Timezone Governance Service (Milestone M6).

Provides IANA timezone validation, daylight-saving-aware window checks, and deterministic
UTC next-window opening calculation for campaign initial dispatches and follow-up sequences.
"""
from datetime import datetime, time, timedelta, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

TIME_FORMAT_REGEX = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class SendingWindowConfig(BaseModel):
    """Structured configuration defining allowed sending windows and timezone."""
    enabled: bool = Field(default=False, description="Whether the sending window constraint is active")
    timezone: str = Field(default="UTC", description="IANA timezone identifier (e.g. 'Asia/Kolkata', 'America/New_York')")
    days: List[int] = Field(
        default_factory=lambda: [1, 2, 3, 4, 5],
        description="Permitted ISO weekdays (1 = Monday, 7 = Sunday)",
    )
    start_time: str = Field(default="09:00", description="Daily window opening time in local HH:MM (inclusive)")
    end_time: str = Field(default="17:00", description="Daily window closing time in local HH:MM (exclusive)")

    model_config = ConfigDict(extra="forbid")

    @field_validator("timezone")
    @classmethod
    def validate_iana_timezone(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Timezone cannot be empty.")
        clean_tz = v.strip()
        try:
            ZoneInfo(clean_tz)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Invalid IANA timezone identifier: '{clean_tz}'.") from exc
        return clean_tz

    @field_validator("days")
    @classmethod
    def validate_iso_days(cls, v: List[int]) -> List[int]:
        if not v:
            raise ValueError("Permitted sending days cannot be empty.")
        cleaned = []
        for day in v:
            if not isinstance(day, int) or day < 1 or day > 7:
                raise ValueError(f"Day {day} is invalid. ISO weekdays must be integers between 1 (Monday) and 7 (Sunday).")
            if day not in cleaned:
                cleaned.append(day)
        cleaned.sort()
        return cleaned

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        if not isinstance(v, str) or not TIME_FORMAT_REGEX.match(v.strip()):
            raise ValueError(f"Time value '{v}' must be in 24-hour HH:MM format (00:00 to 23:59).")
        return v.strip()

    @model_validator(mode="after")
    def validate_window_span(self) -> "SendingWindowConfig":
        if self.enabled:
            # Parse start and end times to compare
            s_match = TIME_FORMAT_REGEX.match(self.start_time)
            e_match = TIME_FORMAT_REGEX.match(self.end_time)
            if s_match and e_match:
                s_hour, s_minute = int(s_match.group(1)), int(s_match.group(2))
                e_hour, e_minute = int(e_match.group(1)), int(e_match.group(2))
                s_time = time(s_hour, s_minute)
                e_time = time(e_hour, e_minute)
                if s_time >= e_time:
                    raise ValueError(
                        f"start_time ({self.start_time}) must be strictly earlier than end_time ({self.end_time})."
                    )
        return self


class SendingWindowService:
    """Service providing safe evaluation and calculation of campaign sending windows."""

    @classmethod
    def parse_config(
        cls,
        raw_config: Optional[Union[SendingWindowConfig, Dict[str, Any]]],
    ) -> Optional[SendingWindowConfig]:
        """Parse and validate raw configuration, returning None if missing or disabled."""
        if raw_config is None:
            return None
        if isinstance(raw_config, SendingWindowConfig):
            return raw_config
        try:
            return SendingWindowConfig.model_validate(raw_config)
        except Exception as exc:
            logger.error("Failed to parse SendingWindowConfig: %s", exc)
            raise ValueError(f"Invalid sending window configuration: {exc}") from exc

    @classmethod
    def is_within_sending_window(
        cls,
        dt_utc: datetime,
        raw_config: Optional[Union[SendingWindowConfig, Dict[str, Any]]],
    ) -> bool:
        """Evaluate whether a UTC datetime falls inside the allowed sending window.
        
        Guarantees:
        - If config is None or disabled: returns True (unrestricted sending).
        - Inclusive of start_time, exclusive of end_time: [start_time, end_time).
        - If config is corrupt or invalid: fails safely by returning False and logging an error.
          Never sends outside or under an invalid configuration.
        """
        if raw_config is None:
            return True

        try:
            config = cls.parse_config(raw_config)
        except Exception as exc:
            logger.critical("Sending window configuration is corrupt/invalid: %s. Refusing dispatch.", exc)
            return False

        if config is None or not config.enabled:
            return True

        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)

        try:
            tz = ZoneInfo(config.timezone)
        except Exception as exc:
            logger.critical("Configured timezone '%s' could not be loaded: %s. Refusing dispatch.", config.timezone, exc)
            return False

        dt_local = dt_utc.astimezone(tz)

        # 1. Day of week check (ISO weekday: 1 = Monday .. 7 = Sunday)
        if dt_local.isoweekday() not in config.days:
            return False

        # 2. Local time of day check
        s_match = TIME_FORMAT_REGEX.match(config.start_time)
        e_match = TIME_FORMAT_REGEX.match(config.end_time)
        if not s_match or not e_match:
            return False

        start_t = time(int(s_match.group(1)), int(s_match.group(2)))
        end_t = time(int(e_match.group(1)), int(e_match.group(2)))
        local_t = dt_local.time()

        return start_t <= local_t < end_t

    @classmethod
    def compute_next_window_opening(
        cls,
        ref_dt_utc: datetime,
        raw_config: Optional[Union[SendingWindowConfig, Dict[str, Any]]],
    ) -> datetime:
        """Compute the next valid sending window opening in UTC for a given reference timestamp.
        
        Rules:
        - If config is None or disabled: returns ref_dt_utc directly.
        - If ref_dt_utc is already within the window: returns ref_dt_utc.
        - If ref_dt_local is before today's window and today is a permitted day: returns today's opening in UTC.
        - If ref_dt_local is after today's window (or today is not permitted): iterates up to 14 days
          to find the next permitted day and returns its opening in UTC.
        - Fails closed: raises ValueError if configuration is corrupt/invalid rather than returning
          an arbitrary fallback.
        - Deterministic DST policy: Uses fold=0 on local datetime creation for ambiguous transition times.
        """
        if raw_config is None:
            return ref_dt_utc

        config = cls.parse_config(raw_config)
        if config is None or not config.enabled:
            return ref_dt_utc

        if ref_dt_utc.tzinfo is None:
            ref_dt_utc = ref_dt_utc.replace(tzinfo=timezone.utc)

        tz = ZoneInfo(config.timezone)
        ref_local = ref_dt_utc.astimezone(tz)

        s_match = TIME_FORMAT_REGEX.match(config.start_time)
        e_match = TIME_FORMAT_REGEX.match(config.end_time)
        if not s_match or not e_match:
            raise ValueError(f"Invalid time format in config: {config.start_time} - {config.end_time}")

        start_t = time(int(s_match.group(1)), int(s_match.group(2)))
        end_t = time(int(e_match.group(1)), int(e_match.group(2)))

        local_date = ref_local.date()

        # Check today (day_offset = 0)
        if local_date.isoweekday() in config.days:
            # If currently before start_time: today's start_time is the opening
            if ref_local.time() < start_t:
                opening_local = datetime.combine(local_date, start_t, tzinfo=tz).replace(fold=0)
                return opening_local.astimezone(timezone.utc)
            # If inside the window: already valid
            elif ref_local.time() < end_t:
                return ref_dt_utc
            # Else: window has closed for today, check subsequent days

        # Check subsequent days (day_offset 1..14)
        for offset in range(1, 15):
            candidate_date = local_date + timedelta(days=offset)
            if candidate_date.isoweekday() in config.days:
                opening_local = datetime.combine(candidate_date, start_t, tzinfo=tz).replace(fold=0)
                return opening_local.astimezone(timezone.utc)

        raise ValueError(f"Could not find valid window opening within 14 days for config: {config}")

