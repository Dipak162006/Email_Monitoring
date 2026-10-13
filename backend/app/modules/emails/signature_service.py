import logging
import re
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.sanitizer import sanitize_html
from app.modules.auth.models import User
from app.modules.companies.models import CompanyRole
from app.modules.companies.service import CompanyService
from app.modules.email_accounts.models import EmailAccount
from app.modules.email_accounts.service import EmailAccountService
from app.modules.emails.models import Email, EmailSignature, EmailStatus
from app.modules.emails.schemas import EmailSignatureCreate, EmailSignatureUpdate

logger = logging.getLogger(__name__)


class SignatureService:
    """Service layer managing email signatures, default signatures, authorization,
    and integration into email composition, drafts, and templates.
    """

    @classmethod
    async def create_signature(
        cls,
        db: AsyncSession,
        current_user: User,
        signature_in: EmailSignatureCreate,
        company_id: Optional[int] = None,
        account_id: Optional[int] = None,
    ) -> EmailSignature:
        """Create a new email signature for an authorized email account."""
        # 1. Resolve effective account_id
        effective_account_id: Optional[int] = account_id or signature_in.email_account_id
        if effective_account_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="email_account_id is required to create a signature.",
            )

        # 2. Fetch email account and verify state
        account = await EmailAccountService.get_email_account(db, effective_account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email account not found.",
            )

        if not account.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email account is inactive.",
            )

        # 3. Resolve and verify company
        effective_company_id = account.company_id
        if company_id is not None and company_id != effective_company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email account does not belong to the specified company.",
            )

        # 4. Verify company membership
        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=effective_company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not belong to the company that owns this email account.",
            )

        # 5. Check user access to account
        has_access = await EmailAccountService.check_user_access(
            db=db,
            account=account,
            user_id=current_user.id,
            user_role=membership.role,
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access signatures for this email account.",
            )

        # 6. If setting as default, unset any existing default signature for this account
        if signature_in.is_default:
            # Lock parent EmailAccount row with SELECT ... FOR UPDATE so default changes for the same account are serialized
            await db.execute(
                select(EmailAccount.id)
                .where(EmailAccount.id == effective_account_id)
                .with_for_update()
            )
            await db.execute(
                update(EmailSignature)
                .where(
                    EmailSignature.email_account_id == effective_account_id,
                    EmailSignature.is_default == True,
                )
                .values(is_default=False)
            )

        sanitized_html = sanitize_html(signature_in.body_html) if signature_in.body_html else None

        # 7. Create signature
        signature = EmailSignature(
            company_id=effective_company_id,
            email_account_id=effective_account_id,
            user_id=current_user.id,
            name=signature_in.name,
            body_text=signature_in.body_text,
            body_html=sanitized_html,
            is_default=signature_in.is_default,
        )
        db.add(signature)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            logger.warning(
                "IntegrityError when creating default signature for account_id=%d: %s",
                effective_account_id,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A default signature already exists or is concurrently being set for this email account.",
            )
        await db.refresh(signature)
        logger.info(
            "Created signature id=%d (name='%s', account_id=%d, default=%s) by user id=%d",
            signature.id,
            signature.name,
            effective_account_id,
            signature.is_default,
            current_user.id,
        )
        return signature

    @classmethod
    async def list_signatures(
        cls,
        db: AsyncSession,
        current_user: User,
        company_id: Optional[int] = None,
        account_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[EmailSignature], int]:
        """List signatures for authorized accounts/companies with pagination."""
        if account_id is not None:
            account = await EmailAccountService.get_email_account(db, account_id)
            if not account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Email account not found.",
                )
            if company_id is not None and account.company_id != company_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email account does not belong to the specified company.",
                )

            membership = await CompanyService.get_user_membership(
                db=db,
                company_id=account.company_id,
                user_id=current_user.id,
            )
            if not membership:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not belong to the company that owns this email account.",
                )

            has_access = await EmailAccountService.check_user_access(
                db=db,
                account=account,
                user_id=current_user.id,
                user_role=membership.role,
            )
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to access signatures for this email account.",
                )

            base_query = select(EmailSignature).where(EmailSignature.email_account_id == account_id)
            count_query = select(func.count(EmailSignature.id)).where(EmailSignature.email_account_id == account_id)
            if company_id is not None:
                base_query = base_query.where(EmailSignature.company_id == company_id)
                count_query = count_query.where(EmailSignature.company_id == company_id)

            total_res = await db.execute(count_query)
            total = total_res.scalar() or 0

            signatures_res = await db.execute(
                base_query.order_by(EmailSignature.is_default.desc(), EmailSignature.created_at.asc())
                .limit(limit)
                .offset(offset)
            )
            return list(signatures_res.scalars().all()), total

        # No specific account_id: filter by company_id or all user companies
        accessible_account_ids: List[int] = []

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
            accounts = await EmailAccountService.get_user_accessible_accounts_for_company(
                db=db,
                company_id=company_id,
                user_id=current_user.id,
                user_role=membership.role,
            )
            accessible_account_ids = [a.id for a in accounts]
        else:
            user_companies = await CompanyService.get_user_companies(db, current_user.id)
            for comp, comp_user in user_companies:
                accounts = await EmailAccountService.get_user_accessible_accounts_for_company(
                    db=db,
                    company_id=comp.id,
                    user_id=current_user.id,
                    user_role=comp_user,
                )
                accessible_account_ids.extend([a.id for a in accounts])

        if not accessible_account_ids:
            return [], 0

        base_query = select(EmailSignature).where(EmailSignature.email_account_id.in_(accessible_account_ids))
        count_query = select(func.count(EmailSignature.id)).where(EmailSignature.email_account_id.in_(accessible_account_ids))
        if company_id is not None:
            base_query = base_query.where(EmailSignature.company_id == company_id)
            count_query = count_query.where(EmailSignature.company_id == company_id)

        total_res = await db.execute(count_query)
        total = total_res.scalar() or 0

        signatures_res = await db.execute(
            base_query.order_by(EmailSignature.is_default.desc(), EmailSignature.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(signatures_res.scalars().all()), total

    @classmethod
    async def copy_signature(
        cls,
        db: AsyncSession,
        current_user: User,
        signature_id: int,
        target_account_id: int,
        new_name: Optional[str] = None,
        make_default: bool = False,
    ) -> EmailSignature:
        """Copy an email signature to another email account with strict authorization,
        company isolation, idempotency, and preservation of existing signatures.
        """
        # 1. Fetch source signature
        source_sig = await db.get(EmailSignature, signature_id)
        if not source_sig:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source signature not found.",
            )

        # 2. Check source company membership and account access
        source_membership = await CompanyService.get_user_membership(
            db=db,
            company_id=source_sig.company_id,
            user_id=current_user.id,
        )
        if not source_membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not belong to the company that owns this signature.",
            )

        source_account = await EmailAccountService.get_email_account(db, source_sig.email_account_id)
        if not source_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source email account not found.",
            )

        has_source_access = await EmailAccountService.check_user_access(
            db=db,
            account=source_account,
            user_id=current_user.id,
            user_role=source_membership.role,
        )
        if not has_source_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access the source signature's account.",
            )

        # 3. Fetch and validate target email account
        target_account = await EmailAccountService.get_email_account(db, target_account_id)
        if not target_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target email account not found.",
            )

        if not target_account.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target email account is inactive.",
            )

        # 4. Enforce strict company isolation: cannot copy signatures across different companies
        if target_account.company_id != source_sig.company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot copy signature to an account in a different company.",
            )

        # 5. Check target account access
        has_target_access = await EmailAccountService.check_user_access(
            db=db,
            account=target_account,
            user_id=current_user.id,
            user_role=source_membership.role,
        )
        if not has_target_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to create signatures for the target email account.",
            )

        # 6. Idempotency Check: if target account already has an identical signature (matching body_html and body_text), reuse it!
        stmt_existing = select(EmailSignature).where(
            EmailSignature.email_account_id == target_account_id,
            EmailSignature.body_html == source_sig.body_html,
            EmailSignature.body_text == source_sig.body_text,
        )
        res_existing = await db.execute(stmt_existing)
        existing_identical = res_existing.scalars().first()
        if existing_identical:
            logger.info(
                "Idempotent signature copy: target account %d already has identical signature id=%d ('%s')",
                target_account_id,
                existing_identical.id,
                existing_identical.name,
            )
            return existing_identical

        # 7. Safe Name Resolution: prevent accidental duplicate names on target account
        desired_name = (new_name or source_sig.name).strip()
        candidate_name = desired_name
        name_check_stmt = select(EmailSignature.id).where(
            EmailSignature.email_account_id == target_account_id,
            EmailSignature.name == candidate_name,
        )
        res_name = await db.execute(name_check_stmt)
        if res_name.scalar_one_or_none() is not None:
            # Suffix with (Copy) or unique identifier so existing signature isn't collided
            candidate_name = f"{desired_name} (Copy)"
            res_copy = await db.execute(
                select(EmailSignature.id).where(
                    EmailSignature.email_account_id == target_account_id,
                    EmailSignature.name == candidate_name,
                )
            )
            if res_copy.scalar_one_or_none() is not None:
                candidate_name = f"{desired_name} (from {source_account.name or source_account.email_address})"

        # 8. Default Signature Preservation
        effective_default = False
        if make_default:
            await db.execute(
                select(EmailAccount.id)
                .where(EmailAccount.id == target_account_id)
                .with_for_update()
            )
            await db.execute(
                update(EmailSignature)
                .where(
                    EmailSignature.email_account_id == target_account_id,
                    EmailSignature.is_default == True,
                )
                .values(is_default=False)
            )
            effective_default = True

        # 9. Create copied signature record
        cloned = EmailSignature(
            company_id=source_sig.company_id,
            email_account_id=target_account_id,
            user_id=current_user.id,
            name=candidate_name,
            body_text=source_sig.body_text,
            body_html=source_sig.body_html,
            is_default=effective_default,
        )
        db.add(cloned)
        await db.commit()
        await db.refresh(cloned)

        logger.info(
            "Copied signature id=%d from account %d to account %d as id=%d ('%s', default=%s) by user %d",
            source_sig.id,
            source_sig.email_account_id,
            target_account_id,
            cloned.id,
            cloned.name,
            cloned.is_default,
            current_user.id,
        )
        return cloned

    @classmethod
    async def get_signature(
        cls,
        db: AsyncSession,
        current_user: User,
        signature_id: int,
        company_id: Optional[int] = None,
    ) -> EmailSignature:
        """Fetch a single signature by ID, strictly enforcing authorization."""
        signature = await db.get(EmailSignature, signature_id)
        if not signature:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Signature not found.",
            )

        if company_id is not None and signature.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Signature does not belong to the specified company.",
            )

        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=signature.company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this signature.",
            )

        account = await EmailAccountService.get_email_account(db, signature.email_account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated email account not found.",
            )

        has_access = await EmailAccountService.check_user_access(
            db=db,
            account=account,
            user_id=current_user.id,
            user_role=membership.role,
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this signature.",
            )

        return signature

    @classmethod
    async def update_signature(
        cls,
        db: AsyncSession,
        current_user: User,
        signature_id: int,
        signature_in: EmailSignatureUpdate,
        company_id: Optional[int] = None,
    ) -> EmailSignature:
        """Update fields of an existing signature ensuring authorization and default integrity."""
        signature = await cls.get_signature(db, current_user, signature_id, company_id)

        # Handle account reassignment if requested
        if signature_in.email_account_id is not None and signature_in.email_account_id != signature.email_account_id:
            new_account = await EmailAccountService.get_email_account(db, signature_in.email_account_id)
            if not new_account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Target email account not found.",
                )
            if new_account.company_id != signature.company_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot move signature to an email account in a different company.",
                )
            membership = await CompanyService.get_user_membership(db, signature.company_id, current_user.id)
            has_access = await EmailAccountService.check_user_access(
                db=db,
                account=new_account,
                user_id=current_user.id,
                user_role=membership.role,
            )
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to access the target email account.",
                )
            signature.email_account_id = new_account.id

        if signature_in.name is not None:
            signature.name = signature_in.name
        if signature_in.body_text is not None:
            signature.body_text = signature_in.body_text
        if signature_in.body_html is not None:
            signature.body_html = sanitize_html(signature_in.body_html)

        if signature_in.is_default is not None:
            if signature_in.is_default:
                # Lock parent EmailAccount row with SELECT ... FOR UPDATE so default changes are serialized
                await db.execute(
                    select(EmailAccount.id)
                    .where(EmailAccount.id == signature.email_account_id)
                    .with_for_update()
                )
                # Unset previous default for this account
                await db.execute(
                    update(EmailSignature)
                    .where(
                        EmailSignature.email_account_id == signature.email_account_id,
                        EmailSignature.id != signature.id,
                        EmailSignature.is_default == True,
                    )
                    .values(is_default=False)
                )
                signature.is_default = True
            else:
                signature.is_default = False

        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            logger.warning(
                "IntegrityError when updating default signature id=%d: %s",
                signature.id,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A default signature already exists or is concurrently being set for this email account.",
            )
        await db.refresh(signature)
        logger.info("Updated signature id=%d by user id=%d", signature.id, current_user.id)
        return signature

    @classmethod
    async def delete_signature(
        cls,
        db: AsyncSession,
        current_user: User,
        signature_id: int,
        company_id: Optional[int] = None,
    ) -> None:
        """Delete an email signature."""
        signature = await cls.get_signature(db, current_user, signature_id, company_id)
        await db.delete(signature)
        await db.commit()
        logger.info("Deleted signature id=%d by user id=%d", signature_id, current_user.id)

    @classmethod
    async def set_default_signature(
        cls,
        db: AsyncSession,
        current_user: User,
        signature_id: int,
        company_id: Optional[int] = None,
    ) -> EmailSignature:
        """Designate a signature as the single default for its associated EmailAccount."""
        signature = await cls.get_signature(db, current_user, signature_id, company_id)

        # Lock parent EmailAccount row with SELECT ... FOR UPDATE so default changes are serialized
        await db.execute(
            select(EmailAccount.id)
            .where(EmailAccount.id == signature.email_account_id)
            .with_for_update()
        )

        # Unset all other defaults for this account safely
        await db.execute(
            update(EmailSignature)
            .where(
                EmailSignature.email_account_id == signature.email_account_id,
                EmailSignature.id != signature.id,
                EmailSignature.is_default == True,
            )
            .values(is_default=False)
        )
        signature.is_default = True

        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            logger.warning(
                "IntegrityError when setting default signature id=%d: %s",
                signature.id,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A default signature already exists or is concurrently being set for this email account.",
            )
        await db.refresh(signature)
        logger.info(
            "Set signature id=%d as default for account id=%d by user id=%d",
            signature.id,
            signature.email_account_id,
            current_user.id,
        )
        return signature

    @classmethod
    async def get_default_signature(
        cls,
        db: AsyncSession,
        current_user: User,
        account_id: int,
        company_id: Optional[int] = None,
    ) -> Optional[EmailSignature]:
        """Retrieve the effective default signature for an authorized EmailAccount."""
        account = await EmailAccountService.get_email_account(db, account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email account not found.",
            )

        if company_id is not None and account.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email account does not belong to the specified company.",
            )

        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=account.company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this email account.",
            )

        has_access = await EmailAccountService.check_user_access(
            db=db,
            account=account,
            user_id=current_user.id,
            user_role=membership.role,
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access signatures for this email account.",
            )

        stmt = select(EmailSignature).where(
            EmailSignature.email_account_id == account_id,
            EmailSignature.is_default == True,
        )
        res = await db.execute(stmt)
        return res.scalars().first()

    # -------------------------------------------------------------------------
    # Content Insertion & Deduplication Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def apply_signature_to_content(
        body_text: Optional[str],
        body_html: Optional[str],
        signature: EmailSignature,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Append or insert the signature into plain-text and/or HTML representations.
        
        Preserves existing user content, prevents duplicate signature insertion,
        and respects plain-text vs. HTML formats.
        """
        new_text = body_text
        new_html = body_html

        # 1. Plain-text insertion
        if signature.body_text and signature.body_text.strip():
            sig_text = signature.body_text.strip()
            if not new_text or not new_text.strip():
                new_text = signature.body_text
            elif sig_text not in new_text:
                new_text = f"{new_text}\n\n{signature.body_text}"

        # 2. HTML insertion
        if signature.body_html and signature.body_html.strip():
            sig_html = sanitize_html(signature.body_html.strip())
            if sig_html and sig_html.strip():
                sig_raw_text = signature.body_text.strip() if signature.body_text else None
                # Check if signature already present in HTML
                is_dup = (sig_html in (new_html or "")) or (sig_raw_text and sig_raw_text in (new_html or ""))

                if not is_dup:
                    if not new_html or not new_html.strip():
                        if new_text and new_text != signature.body_text:
                            escaped_text = new_text.replace("\n", "<br>")
                            new_html = f"<div>{escaped_text}</div><br><br>{sig_html}"
                        else:
                            new_html = sig_html
                    else:
                        lower_html = new_html.lower()
                        if "</body>" in lower_html:
                            idx = lower_html.rfind("</body>")
                            new_html = new_html[:idx] + f"<br><br>{sig_html}" + new_html[idx:]
                        else:
                            new_html = f"{new_html}<br><br>{sig_html}"

        elif signature.body_text and signature.body_text.strip() and new_html:
            # Signature only has plain-text, but email has HTML: insert as formatted HTML if not present
            sig_raw_text = signature.body_text.strip()
            if sig_raw_text not in new_html:
                formatted_sig = signature.body_text.replace("\n", "<br>")
                lower_html = new_html.lower()
                if "</body>" in lower_html:
                    idx = lower_html.rfind("</body>")
                    new_html = new_html[:idx] + f"<br><br>{formatted_sig}" + new_html[idx:]
                else:
                    new_html = f"{new_html}<br><br>{formatted_sig}"

        return new_text, new_html

    @classmethod
    async def apply_signature_to_draft(
        cls,
        db: AsyncSession,
        current_user: User,
        draft_id: int,
        signature_id: Optional[int] = None,
        company_id: Optional[int] = None,
    ) -> Email:
        """Apply an authorized signature (or default signature) to an existing draft."""
        draft = await db.get(Email, draft_id)
        if not draft:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft not found.",
            )

        if company_id is not None and draft.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft does not belong to the specified company.",
            )

        if draft.is_deleted or draft.status != EmailStatus.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot apply signature to a deleted or non-draft email.",
            )

        # Verify access
        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=draft.company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this draft.",
            )

        account = await EmailAccountService.get_email_account(db, draft.email_account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated email account not found.",
            )

        has_access = await EmailAccountService.check_user_access(
            db=db,
            account=account,
            user_id=current_user.id,
            user_role=membership.role,
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this draft.",
            )

        # Resolve signature
        target_sig: Optional[EmailSignature] = None
        if signature_id is not None:
            target_sig = await cls.get_signature(db, current_user, signature_id, company_id)
            if target_sig.company_id != draft.company_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Signature belongs to a different company.",
                )
            if target_sig.email_account_id != draft.email_account_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Signature is scoped to a different email account.",
                )
        else:
            target_sig = await cls.get_default_signature(db, current_user, draft.email_account_id, draft.company_id)

        if target_sig:
            updated_text, updated_html = cls.apply_signature_to_content(
                draft.body_text,
                draft.body_html,
                target_sig,
            )
            draft.body_text = updated_text
            draft.body_html = updated_html
            await db.commit()
            await db.refresh(draft)
            logger.info("Applied signature id=%d to draft id=%d", target_sig.id, draft.id)

        return draft
