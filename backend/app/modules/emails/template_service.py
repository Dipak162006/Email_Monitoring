import logging
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.auth.models import User
from app.modules.companies.service import CompanyService
from app.modules.email_accounts.service import EmailAccountService
from app.modules.emails.models import Email, EmailStatus, EmailTemplate
from app.modules.emails.schemas import EmailTemplateCreate, EmailTemplateUpdate

logger = logging.getLogger(__name__)


class EmailTemplateService:
    """Service layer managing reusable email templates and template application to drafts."""

    @classmethod
    async def create_template(
        cls,
        db: AsyncSession,
        current_user: User,
        template_in: EmailTemplateCreate,
        company_id: Optional[int] = None,
    ) -> EmailTemplate:
        """Create a new reusable email template within an authorized company and optional account."""
        # 1. Resolve effective company_id
        effective_company_id: int
        if company_id is not None:
            effective_company_id = company_id
        elif template_in.email_account_id is not None:
            acc = await EmailAccountService.get_email_account(db, template_in.email_account_id)
            if not acc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Email account not found.",
                )
            effective_company_id = acc.company_id
        else:
            user_companies = await CompanyService.get_user_companies(db, current_user.id)
            if not user_companies:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not belong to any company.",
                )
            if len(user_companies) == 1:
                effective_company_id = user_companies[0][0].id
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Multiple company memberships found. Please specify company_id.",
                )

        # 2. Verify user belongs to the company
        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=effective_company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not belong to the specified company.",
            )

        # 3. If account-scoped, verify account existence and user access
        if template_in.email_account_id is not None:
            account = await EmailAccountService.get_email_account(db, template_in.email_account_id)
            if not account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Email account not found.",
                )
            if account.company_id != effective_company_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email account does not belong to the specified company.",
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
                    detail="You do not have permission to create templates for this email account.",
                )

        template = EmailTemplate(
            company_id=effective_company_id,
            email_account_id=template_in.email_account_id,
            user_id=current_user.id,
            name=template_in.name,
            subject=template_in.subject or "",
            body_text=template_in.body_text,
            body_html=template_in.body_html,
            is_active=template_in.is_active,
        )
        db.add(template)
        await db.commit()
        await db.refresh(template)
        logger.info(
            "Created template id=%d name='%s' for company id=%d by user id=%d",
            template.id,
            template.name,
            template.company_id,
            current_user.id,
        )
        return template

    @classmethod
    async def get_template(
        cls,
        db: AsyncSession,
        current_user: User,
        template_id: int,
        company_id: Optional[int] = None,
    ) -> EmailTemplate:
        """Retrieve an email template by ID ensuring company and account authorization."""
        template = await db.get(EmailTemplate, template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email template not found.",
            )

        if company_id is not None and template.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email template not found in the specified company.",
            )

        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=template.company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this email template.",
            )

        if template.email_account_id is not None:
            account = await EmailAccountService.get_email_account(db, template.email_account_id)
            if account:
                has_access = await EmailAccountService.check_user_access(
                    db=db,
                    account=account,
                    user_id=current_user.id,
                    user_role=membership.role,
                )
                if not has_access:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You do not have access to this account-scoped email template.",
                    )

        return template

    @classmethod
    async def list_templates(
        cls,
        db: AsyncSession,
        current_user: User,
        company_id: Optional[int] = None,
        email_account_id: Optional[int] = None,
        is_active: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[EmailTemplate], int]:
        """List email templates accessible to the user with pagination and optional filters."""
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
            accessible_acc_ids = [acc.id for acc in accessible_accs]

            conditions = [EmailTemplate.company_id == company_id]
            if email_account_id is not None:
                if email_account_id not in accessible_acc_ids:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You do not have access to this email account.",
                    )
                conditions.append(EmailTemplate.email_account_id == email_account_id)
            else:
                if accessible_acc_ids:
                    conditions.append(
                        or_(
                            EmailTemplate.email_account_id.is_(None),
                            EmailTemplate.email_account_id.in_(accessible_acc_ids),
                        )
                    )
                else:
                    conditions.append(EmailTemplate.email_account_id.is_(None))
        else:
            user_companies = await CompanyService.get_user_companies(db, current_user.id)
            if not user_companies:
                return [], 0

            company_conditions = []
            for comp, role in user_companies:
                accs = await EmailAccountService.get_user_accessible_accounts_for_company(
                    db=db,
                    company_id=comp.id,
                    user_id=current_user.id,
                    user_role=role,
                )
                acc_ids = [a.id for a in accs]
                if email_account_id is not None:
                    if email_account_id in acc_ids:
                        company_conditions.append(
                            (EmailTemplate.company_id == comp.id)
                            & (EmailTemplate.email_account_id == email_account_id)
                        )
                else:
                    if acc_ids:
                        company_conditions.append(
                            (EmailTemplate.company_id == comp.id)
                            & (
                                or_(
                                    EmailTemplate.email_account_id.is_(None),
                                    EmailTemplate.email_account_id.in_(acc_ids),
                                )
                            )
                        )
                    else:
                        company_conditions.append(
                            (EmailTemplate.company_id == comp.id)
                            & (EmailTemplate.email_account_id.is_(None))
                        )

            if not company_conditions:
                return [], 0
            conditions = [or_(*company_conditions)]

        if is_active is not None:
            conditions.append(EmailTemplate.is_active == is_active)

        count_stmt = select(func.count()).select_from(EmailTemplate).where(*conditions)
        total_res = await db.execute(count_stmt)
        total = total_res.scalar_one()

        items_stmt = (
            select(EmailTemplate)
            .where(*conditions)
            .order_by(EmailTemplate.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items_res = await db.execute(items_stmt)
        templates = list(items_res.scalars().all())
        return templates, total

    @classmethod
    async def update_template(
        cls,
        db: AsyncSession,
        current_user: User,
        template_id: int,
        template_update: EmailTemplateUpdate,
        company_id: Optional[int] = None,
    ) -> EmailTemplate:
        """Update an existing template's name, content, account scope, or active state."""
        template = await cls.get_template(db, current_user, template_id, company_id)

        if template_update.email_account_id is not None:
            acc = await EmailAccountService.get_email_account(db, template_update.email_account_id)
            if not acc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Email account not found.",
                )
            if acc.company_id != template.company_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email account does not belong to the template's company.",
                )
            membership = await CompanyService.get_user_membership(
                db=db,
                company_id=template.company_id,
                user_id=current_user.id,
            )
            has_access = await EmailAccountService.check_user_access(
                db=db,
                account=acc,
                user_id=current_user.id,
                user_role=membership.role if membership else "",
            )
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to the target email account.",
                )
            template.email_account_id = template_update.email_account_id

        if template_update.name is not None:
            template.name = template_update.name
        if template_update.subject is not None:
            template.subject = template_update.subject
        if template_update.body_text is not None:
            template.body_text = template_update.body_text
        if template_update.body_html is not None:
            template.body_html = template_update.body_html
        if template_update.is_active is not None:
            template.is_active = template_update.is_active

        await db.commit()
        await db.refresh(template)
        logger.info("Updated template id=%d by user id=%d", template.id, current_user.id)
        return template

    @classmethod
    async def delete_template(
        cls,
        db: AsyncSession,
        current_user: User,
        template_id: int,
        company_id: Optional[int] = None,
    ) -> None:
        """Delete an email template from the database."""
        template = await cls.get_template(db, current_user, template_id, company_id)
        await db.delete(template)
        await db.commit()
        logger.info("Deleted template id=%d by user id=%d", template_id, current_user.id)

    @classmethod
    async def toggle_active(
        cls,
        db: AsyncSession,
        current_user: User,
        template_id: int,
        is_active: Optional[bool] = None,
        company_id: Optional[int] = None,
    ) -> EmailTemplate:
        """Toggle or set the active status of an email template."""
        template = await cls.get_template(db, current_user, template_id, company_id)
        if is_active is not None:
            template.is_active = is_active
        else:
            template.is_active = not template.is_active

        await db.commit()
        await db.refresh(template)
        logger.info("Toggled template id=%d active=%s by user id=%d", template.id, template.is_active, current_user.id)
        return template

    @classmethod
    async def apply_template_to_draft(
        cls,
        db: AsyncSession,
        current_user: User,
        draft_id: int,
        template_id: int,
        company_id: Optional[int] = None,
        signature_id: Optional[int] = None,
    ) -> Email:
        """Apply a reusable template to an existing draft email.
        
        Copies subject, body_text, and body_html into the draft.
        Preserves recipients, thread/reply metadata, and keeps draft status as DRAFT.
        Rejects inactive templates, non-draft/deleted emails, and cross-company/account templates.
        """
        # 1. Fetch draft and validate state
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
                detail="Cannot apply template to a deleted or non-draft email.",
            )

        # 2. Verify user access to draft
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

        # 3. Fetch template ensuring authorization
        template = await cls.get_template(db, current_user, template_id, company_id)

        # 4. Check company boundary
        if draft.company_id != template.company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Draft and template belong to different companies.",
            )

        # 5. Check account scope matching
        if template.email_account_id is not None and template.email_account_id != draft.email_account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Template is scoped to a different email account.",
            )

        # 6. Verify template is active
        if not template.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot apply an inactive email template.",
            )

        # 7. Copy template content into draft
        draft.subject = template.subject or ""
        draft.body_text = template.body_text
        draft.body_html = template.body_html

        # 8. M11 Signature Integration: Apply selected or default signature
        from app.modules.emails.signature_service import SignatureService
        target_sig = None
        if signature_id is not None:
            target_sig = await SignatureService.get_signature(
                db=db,
                current_user=current_user,
                signature_id=signature_id,
                company_id=draft.company_id,
            )
            if target_sig.company_id != draft.company_id or target_sig.email_account_id != draft.email_account_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Signature does not belong to this draft's email account.",
                )
        else:
            target_sig = await SignatureService.get_default_signature(
                db=db,
                current_user=current_user,
                account_id=draft.email_account_id,
                company_id=draft.company_id,
            )

        if target_sig:
            updated_text, updated_html = SignatureService.apply_signature_to_content(
                draft.body_text,
                draft.body_html,
                target_sig,
            )
            draft.body_text = updated_text
            draft.body_html = updated_html

        # Ensure draft remains DRAFT
        draft.status = EmailStatus.DRAFT.value

        await db.commit()
        await db.refresh(draft)
        logger.info(
            "Applied template id=%d to draft id=%d by user id=%d",
            template.id,
            draft.id,
            current_user.id,
        )
        return draft
