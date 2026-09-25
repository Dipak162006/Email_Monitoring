from datetime import datetime, timedelta, timezone
import logging
from typing import Dict, List, Optional, Set, Tuple
from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.companies.service import CompanyService
from app.modules.email_accounts.models import EmailAccount
from app.modules.email_accounts.service import EmailAccountService
from app.modules.emails.dependencies import verify_user_can_access_account
from app.modules.emails.models import Email, EmailDirection, EmailStatus, EmailThread
from app.modules.emails.schemas import (
    AccountHealthItem,
    AccountHealthResponse,
    DashboardActivityPoint,
    DashboardActivityResponse,
    DashboardStatsResponse,
)

logger = logging.getLogger(__name__)


class DashboardService:
    """Service providing aggregated operational statistics, activity time-series,
    and account health metrics for the Email Monitoring Dashboard.
    """

    @classmethod
    async def _resolve_authorized_account_ids(
        cls,
        db: AsyncSession,
        current_user: User,
        company_id: Optional[int] = None,
        email_account_id: Optional[int] = None,
    ) -> List[int]:
        """Resolve and verify the list of email account IDs the user is authorized to access."""
        if company_id is not None:
            membership = await CompanyService.get_user_membership(
                db=db,
                company_id=company_id,
                user_id=current_user.id,
            )
            if not membership:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not belong to the specified company.",
                )

            accessible_accs = await EmailAccountService.get_user_accessible_accounts_for_company(
                db=db,
                company_id=company_id,
                user_id=current_user.id,
                user_role=membership.role,
            )
            accessible_ids = [acc.id for acc in accessible_accs]

            if email_account_id is not None:
                if email_account_id not in accessible_ids:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You do not have access to this email account.",
                    )
                return [email_account_id]
            return accessible_ids

        # Cross-company scope for current user
        if email_account_id is not None:
            account = await verify_user_can_access_account(
                db=db,
                current_user=current_user,
                account_id=email_account_id,
            )
            return [account.id]

        all_accounts = await EmailAccountService.get_all_user_authorized_accounts(
            db=db,
            user_id=current_user.id,
        )
        return [acc.id for acc in all_accounts]

    @classmethod
    def _normalize_date_range(
        cls,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        all_time: bool = False,
        default_to_7d: bool = False,
    ) -> Tuple[Optional[datetime], datetime]:
        """Normalize date boundaries to UTC and handle time windows including All Time.
        
        - If all_time is True: resolved_from is None (no lower date boundary).
        - If date_from is explicitly provided: validates and normalizes it to UTC.
        - If date_from is omitted (None):
            - If default_to_7d is True: defaults to last 7 days.
            - Otherwise: resolved_from is None (complete available history / All Time).
        """
        now = datetime.now(timezone.utc)
        resolved_to = date_to if date_to is not None else now
        if resolved_to.tzinfo is None:
            resolved_to = resolved_to.replace(tzinfo=timezone.utc)

        if all_time:
            return None, resolved_to

        if date_from is not None:
            resolved_from = date_from
            if resolved_from.tzinfo is None:
                resolved_from = resolved_from.replace(tzinfo=timezone.utc)

            if resolved_from > resolved_to:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="date_from cannot be later than date_to.",
                )
            return resolved_from, resolved_to

        if default_to_7d:
            resolved_from = resolved_to - timedelta(days=7)
            return resolved_from, resolved_to

        return None, resolved_to

    @classmethod
    async def get_dashboard_stats(
        cls,
        db: AsyncSession,
        current_user: User,
        company_id: Optional[int] = None,
        email_account_id: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        all_time: bool = False,
    ) -> DashboardStatsResponse:
        """Calculate primary email operational metrics for the current period
        and compute comparisons against the previous equivalent time window.
        When all_time is True or date_from is omitted, queries complete available history.
        """
        account_ids = await cls._resolve_authorized_account_ids(
            db=db,
            current_user=current_user,
            company_id=company_id,
            email_account_id=email_account_id,
        )

        resolved_from, resolved_to = cls._normalize_date_range(
            date_from, date_to, all_time=all_time, default_to_7d=False
        )

        if not account_ids:
            return DashboardStatsResponse(
                sent_count=0,
                bounced_count=0,
                response_count=0,
                bounce_rate=0.0,
                sent_change_percent=None,
                bounced_change_percent=None,
                response_change_percent=None,
                period_start=resolved_from,
                period_end=resolved_to,
            )

        effective_ts = func.coalesce(Email.received_at, Email.sent_at, Email.created_at)

        # Helper to query counts
        async def query_counts(start: Optional[datetime], end: datetime) -> Tuple[int, int, int]:
            # Sent count: OUTGOING + SENT
            sent_stmt = (
                select(func.count(Email.id))
                .where(
                    Email.email_account_id.in_(account_ids),
                    Email.direction == EmailDirection.OUTGOING.value,
                    Email.status == EmailStatus.SENT.value,
                    Email.is_deleted == False,
                    effective_ts <= end,
                )
            )
            if start is not None:
                sent_stmt = sent_stmt.where(effective_ts >= start)
            sent_res = await db.execute(sent_stmt)
            sent = sent_res.scalar() or 0

            # Bounced count: BOUNCED
            bounced_stmt = (
                select(func.count(Email.id))
                .where(
                    Email.email_account_id.in_(account_ids),
                    Email.status == EmailStatus.BOUNCED.value,
                    Email.is_deleted == False,
                    effective_ts <= end,
                )
            )
            if start is not None:
                bounced_stmt = bounced_stmt.where(effective_ts >= start)
            bounced_res = await db.execute(bounced_stmt)
            bounced = bounced_res.scalar() or 0

            # Response count: INCOMING + parent thread has_reply == True
            resp_stmt = (
                select(func.count(Email.id))
                .join(EmailThread, Email.thread_id == EmailThread.id)
                .where(
                    Email.email_account_id.in_(account_ids),
                    Email.direction == EmailDirection.INCOMING.value,
                    EmailThread.has_reply == True,
                    Email.is_deleted == False,
                    effective_ts <= end,
                )
            )
            if start is not None:
                resp_stmt = resp_stmt.where(effective_ts >= start)
            resp_res = await db.execute(resp_stmt)
            resp = resp_res.scalar() or 0

            return sent, bounced, resp

        curr_sent, curr_bounced, curr_resp = await query_counts(resolved_from, resolved_to)

        # Equivalent previous period calculation (only possible if resolved_from is bounded)
        if resolved_from is not None:
            duration = resolved_to - resolved_from
            prev_to = resolved_from
            prev_from = resolved_from - duration
            prev_sent, prev_bounced, prev_resp = await query_counts(prev_from, prev_to)
        else:
            prev_sent, prev_bounced, prev_resp = 0, 0, 0

        # Bounce rate calculation
        bounce_rate = round((curr_bounced / curr_sent * 100.0), 2) if curr_sent > 0 else 0.0

        # Safe percentage change calculation
        def calculate_change(curr: int, prev: int) -> Optional[float]:
            if resolved_from is None:
                return None
            if prev > 0:
                return round(((curr - prev) / prev * 100.0), 1)
            return None

        return DashboardStatsResponse(
            sent_count=curr_sent,
            bounced_count=curr_bounced,
            response_count=curr_resp,
            bounce_rate=bounce_rate,
            sent_change_percent=calculate_change(curr_sent, prev_sent),
            bounced_change_percent=calculate_change(curr_bounced, prev_bounced),
            response_change_percent=calculate_change(curr_resp, prev_resp),
            period_start=resolved_from,
            period_end=resolved_to,
        )

    @classmethod
    async def get_activity_trends(
        cls,
        db: AsyncSession,
        current_user: User,
        company_id: Optional[int] = None,
        email_account_id: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        all_time: bool = False,
    ) -> DashboardActivityResponse:
        """Aggregate daily email counts (sent, responses, bounced) across the date range."""
        account_ids = await cls._resolve_authorized_account_ids(
            db=db,
            current_user=current_user,
            company_id=company_id,
            email_account_id=email_account_id,
        )

        resolved_from, resolved_to = cls._normalize_date_range(
            date_from, date_to, all_time=all_time, default_to_7d=True
        )

        effective_ts = func.coalesce(Email.received_at, Email.sent_at, Email.created_at)

        if resolved_from is None and account_ids:
            # All-time mode: look up earliest email date in authorized accounts
            min_stmt = (
                select(func.min(effective_ts))
                .where(
                    Email.email_account_id.in_(account_ids),
                    Email.is_deleted == False,
                )
            )
            min_res = await db.execute(min_stmt)
            earliest = min_res.scalar()
            if earliest is not None:
                if earliest.tzinfo is None:
                    earliest = earliest.replace(tzinfo=timezone.utc)
                resolved_from = earliest
            else:
                resolved_from = resolved_to - timedelta(days=7)
        elif resolved_from is None:
            resolved_from = resolved_to - timedelta(days=7)

        # Generate calendar days list
        start_date = resolved_from.date()
        end_date = resolved_to.date()
        day_count = (end_date - start_date).days + 1
        if day_count <= 0:
            day_count = 1
            start_date = end_date

        calendar_days = [start_date + timedelta(days=i) for i in range(day_count)]
        date_keys = [d.isoformat() for d in calendar_days]

        if not account_ids or not calendar_days:
            points = [
                DashboardActivityPoint(
                    date=d.isoformat(),
                    label=d.strftime("%a"),
                    sent=0,
                    responses=0,
                    bounced=0,
                )
                for d in calendar_days
            ]
            return DashboardActivityResponse(
                points=points,
                total_sent=0,
                total_responses=0,
                total_bounced=0,
            )

        # 1. Sent emails grouped by day
        sent_stmt = (
            select(func.date(effective_ts).label("day"), func.count(Email.id))
            .where(
                Email.email_account_id.in_(account_ids),
                Email.direction == EmailDirection.OUTGOING.value,
                Email.status == EmailStatus.SENT.value,
                Email.is_deleted == False,
                effective_ts >= resolved_from,
                effective_ts <= resolved_to,
            )
            .group_by("day")
        )
        sent_res = await db.execute(sent_stmt)
        sent_by_day: Dict[str, int] = {str(row[0]): row[1] for row in sent_res.all()}

        # 2. Responses grouped by day
        resp_stmt = (
            select(func.date(effective_ts).label("day"), func.count(Email.id))
            .join(EmailThread, Email.thread_id == EmailThread.id)
            .where(
                Email.email_account_id.in_(account_ids),
                Email.direction == EmailDirection.INCOMING.value,
                EmailThread.has_reply == True,
                Email.is_deleted == False,
                effective_ts >= resolved_from,
                effective_ts <= resolved_to,
            )
            .group_by("day")
        )
        resp_res = await db.execute(resp_stmt)
        resp_by_day: Dict[str, int] = {str(row[0]): row[1] for row in resp_res.all()}

        # 3. Bounced grouped by day
        bounced_stmt = (
            select(func.date(effective_ts).label("day"), func.count(Email.id))
            .where(
                Email.email_account_id.in_(account_ids),
                Email.status == EmailStatus.BOUNCED.value,
                Email.is_deleted == False,
                effective_ts >= resolved_from,
                effective_ts <= resolved_to,
            )
            .group_by("day")
        )
        bounced_res = await db.execute(bounced_stmt)
        bounced_by_day: Dict[str, int] = {str(row[0]): row[1] for row in bounced_res.all()}

        points: List[DashboardActivityPoint] = []
        tot_sent = 0
        tot_resp = 0
        tot_bounced = 0

        for day in calendar_days:
            d_str = day.isoformat()
            s_val = sent_by_day.get(d_str, 0)
            r_val = resp_by_day.get(d_str, 0)
            b_val = bounced_by_day.get(d_str, 0)

            tot_sent += s_val
            tot_resp += r_val
            tot_bounced += b_val

            points.append(
                DashboardActivityPoint(
                    date=d_str,
                    label=day.strftime("%a"),
                    sent=s_val,
                    responses=r_val,
                    bounced=b_val,
                )
            )

        return DashboardActivityResponse(
            points=points,
            total_sent=tot_sent,
            total_responses=tot_resp,
            total_bounced=tot_bounced,
        )

    @classmethod
    async def get_account_health(
        cls,
        db: AsyncSession,
        current_user: User,
        company_id: Optional[int] = None,
    ) -> AccountHealthResponse:
        """Inspect accessible email accounts, active count, and sync timestamps."""
        account_ids = await cls._resolve_authorized_account_ids(
            db=db,
            current_user=current_user,
            company_id=company_id,
        )

        if not account_ids:
            return AccountHealthResponse(
                total_accounts=0,
                active_accounts=0,
                syncing_accounts=0,
                last_synced_at=None,
                accounts=[],
            )

        accounts_stmt = select(EmailAccount).where(EmailAccount.id.in_(account_ids))
        accounts_res = await db.execute(accounts_stmt)
        accounts = list(accounts_res.scalars().all())

        items: List[AccountHealthItem] = []
        active_count = 0
        syncing_count = 0
        latest_sync: Optional[datetime] = None

        for acc in accounts:
            if acc.is_active:
                active_count += 1
                status_label = "Operational"
            else:
                status_label = "Idle"

            if acc.last_synced_at:
                if latest_sync is None or acc.last_synced_at > latest_sync:
                    latest_sync = acc.last_synced_at

            items.append(
                AccountHealthItem(
                    id=acc.id,
                    name=acc.name,
                    email_address=acc.email_address,
                    provider=acc.provider,
                    is_active=acc.is_active,
                    last_synced_at=acc.last_synced_at,
                    status_label=status_label,
                )
            )

        return AccountHealthResponse(
            total_accounts=len(items),
            active_accounts=active_count,
            syncing_accounts=syncing_count,
            last_synced_at=latest_sync,
            accounts=items,
        )
