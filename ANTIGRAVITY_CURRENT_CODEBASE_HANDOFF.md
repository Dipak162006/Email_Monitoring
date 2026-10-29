# ANTIGRAVITY CURRENT CODEBASE MASTER HANDOFF: PULSEMAIL

**Repository**: `Dipak162006/Email_Monitoring`  
**Application Name**: PulseMail (Email Monitoring & Cold Outreach Automation System)  
**Document Generation Date**: October 28, 2026  
**Auditor**: Antigravity Assistant  
**Authoritative Git State**: Branch `master` at commit [`a0f4810ad301df729f1b402dbb88295d692c505a`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring)  
**Database Migration Revision**: `019_add_source_attachment_id` (verified head on runtime PostgreSQL container)  

---

## 1. Quick-Start Context for Incoming AI Assistants

> [!IMPORTANT]
> **Read This First**: This codebase is an active, production-grade email monitoring and campaign outreach system. Do **not** redesign the architecture, rewrite working models, or generate bulk boilerplate. All changes must be incremental, test-backed, and strictly respect tenant isolation (`company_id`).

### Key Facts:
1. **Repository & Architecture**:
   - Backend: Python 3.12, FastAPI, SQLAlchemy 2.0 (asyncio + asyncpg), Alembic, Celery 5.4, Redis 7, PostgreSQL 16.
   - Frontend: React 18, TypeScript, Tailwind CSS, Lucide icons, Vitest, React Router v6.
   - Core Services: SMTP dispatch (`aiosmtplib`), IMAP monitoring (`aioimaplib`), RFC 2822 threading, HTML sanitization (`nh3` / Bleach), Celery Beat periodic scheduler.
2. **Current Implementation Phase**:
   - The system is currently at **Commit `a0f4810`** (*feat(campaigns): add automated multi-step follow-up sequences*).
   - Core follow-up sequence execution, delayed scheduling, email threading, genuine reply detection, bounce/unsubscribe auto-stopping, and worker concurrency controls are **implemented, active, and covered by 10/10 passing tests** in [`backend/tests/test_followup_hardening.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/tests/test_followup_hardening.py).
   - **Crucial Distinction**: The upcoming operational controls (per-recipient stop/skip/reschedule, sending windows/timezones, step-level test sends, and step analytics funnel) exist as an experimental snapshot in `stash@{0}` and branch `backup/m14-5-work-pre-rollback`, but were rolled back from `master` to preserve stability. Do not claim they are present on `master` until cherry-picked and verified.
3. **Primary Working Rule**:
   - **Zero Regression Principle**: Verify against `test_followup_hardening.py` and frontend vitest suites before and after any modification. Always check tenant scoping (`company_id`). Never expose un-sanitized HTML or allow cross-tenant data access.

---

## 2. Verified Repository and Git State

### Git Metadata
- **Current Branch**: `master`
- **Current HEAD**: `a0f4810` — *feat(campaigns): add automated multi-step follow-up sequences*
- **Safety Backup Branch**: `backup/m14-5-work-pre-rollback` (points to `a0f4810`)
- **Remote Origin**: `remotes/origin/master` (points to `9d06bef`)
- **Git Stash**:
  - `stash@{0}: On master: backup-m14.1-m14.5-campaign-work` (contains 21 modified files with M14.1–M14.5 experimental features: per-recipient controls, sending windows, step test-send, and step analytics).
- **Working Tree State**:
  - `repomix-output.xml` (modified, preserved repository digest).
  - No application code, test, configuration, or migration files are staged or uncommitted.

### Last 10 Commits on `master`:
1. `a0f4810` — `feat(campaigns): add automated multi-step follow-up sequences`
2. `833d6a7` — `feat: add mailbox reply-all and forward attachments with row-locked copy safeguards`
3. `6e7d7c1` — `feat: harden campaign follow-up step schema, recipient lifecycle, and SMTP reconciliation`
4. `3adc11c` — `feat: add company suppression list management UI in campaigns`
5. `d361db7` — `feat: add live campaign delivery telemetry and wizard signature/merge-tag support`
6. `9d06bef` — `feat: implement campaign delivery breakdown telemetry and wizard signature insertion`
7. `295fc2c` — `fix: offload DNS verification to threadpool and recover stale SENDING campaign deliveries`
8. `e1f7aef` — `feat: add full campaign merge-tag engine, RFC 8058 unsubscribe, and bounce sync`
9. `d337a7d` — `feat: upgrade template editor with docked inspectors, paste normalization, and CID media`
10. `da663db` — `fix: harden migration test isolation and email body rendering`

---

## 3. Complete Repository Inventory

The codebase contains 176 backend source files, 154 frontend source files, 69 backend test files, and 11 frontend test suites.

### 3.1 Backend Application Layout (`backend/app/`)
- **`core/`**:
  - [`config.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/core/config.py): Pydantic `Settings` loading environment variables (`DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `ALGORITHM`, SMTP/IMAP defaults).
  - [`database.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/core/database.py): Async engine and session factory (`async_sessionmaker`, `create_async_engine`).
  - [`security.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/core/security.py): Password hashing (Argon2 / bcrypt) and JWT token generation/validation.
  - [`auth.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/core/auth.py): FastAPI dependencies: `get_current_user`, `get_company_membership`, `require_company_admin_or_owner`.
- **`modules/auth/`**:
  - User authentication, JWT tokens, password reset flows, refresh tokens, user registration.
- **`modules/companies/`**:
  - Multi-tenant company entities, membership associations (`OWNER`, `ADMIN`, `MEMBER`), invitations, domain association.
- **`modules/email_accounts/`**:
  - Connected SMTP/IMAP credentials, encryption at rest using Fernet, daily rate limit counters, OAuth2 tokens (Gmail/Outlook), connection validation.
- **`modules/domains/`**:
  - Domain records, DNS verification (SPF, DKIM, DMARC, MX) using `dnspython` with asynchronous threadpool offloading.
- **`modules/emails/`**:
  - [`models.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/emails/models.py): `Email`, `EmailThread`, `EmailAttachment`, `EmailTemplate`, `EmailSignature`.
  - [`smtp_service.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/emails/smtp_service.py): Live outbound email dispatch using `aiosmtplib`, MIME composition, attachment encoding, rate-limiting, and error classification.
  - [`imap_service.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/emails/imap_service.py): IMAP inbox synchronization, folder traversal, UID management.
  - [`monitoring_service.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/emails/monitoring_service.py): Background sync processing, email thread grouping, RFC 2822 header inspection (`In-Reply-To`, `References`), genuine reply matching, auto-reply filtering.
- **`modules/campaigns/`**:
  - [`models.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/models.py): `Campaign`, `CampaignStep`, `CampaignRecipient`, `CampaignDelivery`, `SuppressionList`, `CampaignAttachment`.
  - [`schemas.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/schemas.py): Pydantic validation schemas for campaign CRUD, steps, recipients, suppressions, deliveries, and telemetry.
  - [`service.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/service.py): Campaign lifecycle business logic, step synchronization, duplicate detection, launch validation.
  - [`delivery_service.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/delivery_service.py): Orchestrates dispatching of initial step and follow-up steps, pacing delays, stale delivery reconciliation, row-level locking (`with_for_update(skip_locked=True)`).
  - [`preflight_service.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/preflight_service.py): Pre-launch validation (checks email account status, DNS/SPF/DKIM, recipient counts, merge-tag syntax).
  - [`routes.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/routes.py): Authenticated API endpoints for campaign CRUD, steps, recipients, suppressions, launch, pause, cancel.
  - [`public_routes.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/public_routes.py): RFC 8058 one-click unsubscribe and web unsubscribe endpoints (`/api/v1/public/campaigns/unsubscribe`).
- **`workers/`**:
  - [`celery_app.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/workers/celery_app.py): Celery instance setup with Redis broker/result backend; registers Beat schedule (`scheduled-campaign-dispatch-periodic` running every 60s).
  - [`campaign_tasks.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/workers/campaign_tasks.py): Celery task definitions (`scheduled_campaign_dispatch_task`, `dispatch_campaign_batch_task`).
  - [`email_tasks.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/workers/email_tasks.py): Background IMAP mailbox sync tasks.

---

### 3.2 Frontend Application Layout (`frontend/src/`)
- **`pages/`**:
  - `LoginPage.tsx`, `RegisterPage.tsx`, `DashboardPage.tsx`.
  - `MailboxPage.tsx`: Full email client with folder list, thread viewer, conversation history, rich compose modal.
  - `CampaignsPage.tsx`: Campaign list table, status filters, suppression list manager tab.
  - `CreateCampaignPage.tsx`: Multi-step campaign creation wizard (Details, Content & Sequences, Review, Sender selection).
  - `CampaignDetailPage.tsx`: Overview, telemetry metrics, delivery log viewer, follow-up sequence status summary.
  - `CampaignRecipientsPage.tsx`: Recipient table, CSV import modal, manual recipient form.
- **`components/campaigns/`**:
  - `CampaignDetailsStep.tsx`: Name, sender account, sending interval, tracking options.
  - `CampaignContentStep.tsx`: Sequence builder for Step 1 and up to 3 follow-up steps with delay hours and custom subjects/bodies.
  - `CampaignReviewStep.tsx`: Full preflight checklist, configuration summary, launch button.
  - `SuppressionListPanel.tsx`, `AddSuppressionModal.tsx`: Managing suppressed domains and email addresses.
- **`services/`**:
  - `api.ts`: Central Axios client with JWT interceptor, token refresh handler, and typed API namespaces (`campaignsApi`, `emailsApi`, `authApi`, `companiesApi`).

---

## 4. Architecture Decisions & Multi-Tenant Model

```
+---------------------------------------------------------------------------------+
|                               TENANT BOUNDARY                                   |
|                                                                                 |
|   Company (ID, Name, Domain, Settings)                                          |
|      |                                                                          |
|      +---> CompanyMembership (User ID, Company ID, Role: OWNER | ADMIN | MEMBER)  |
|      |                                                                          |
|      +---> EmailAccount (IMAP/SMTP host, encrypted creds, daily limits)          |
|      |                                                                          |
|      +---> Campaign (Subject, Body, Sender ID, Status: DRAFT | RUNNING | ...)   |
|      |        |                                                                 |
|      |        +---> CampaignStep (Step 1..N, delay_hours, subject, body)        |
|      |        +---> CampaignRecipient (Email, status, next_step_due_at)        |
|      |        +---> CampaignDelivery (Step ID, status: SENT | BOUNCED | ...)   |
|      |        +---> SuppressionList (Suppressed email/domain, reason)           |
|      |                                                                          |
|      +---> EmailThread (RFC 2822 In-Reply-To / References grouping)             |
|               +---> Email (Sender, Recipients, Headers, Body, Attachments)      |
+---------------------------------------------------------------------------------+
```

### Critical Architectural Decisions:
1. **Tenant Isolation**: Every database query on `campaigns`, `emails`, `email_accounts`, and `suppression_list` must filter by `company_id`. A user accessing a foreign company's entity receives `404 Not Found` (anti-enumeration).
2. **Step 1 Synchronization**: Step 1 is authoritatively mirrored in `campaign.subject`, `campaign.body_text`, and `campaign.body_html`. Modifying Step 1 updates the campaign root, and vice versa.
3. **Follow-Up Threading**: Every follow-up delivery inspects the recipient's prior successful delivery (`step_number = N - 1`), retrieves its `message_id` and `thread_id`, and dispatches the follow-up with `In-Reply-To: <prior_message_id>` and matching `References`.
4. **Idempotency & Concurrency**:
   - Deliveries enforce `UNIQUE (campaign_id, recipient_id, step_id)`.
   - Polling workers use `SELECT ... FOR UPDATE SKIP LOCKED` on `campaign_recipients`.
   - Row-level database locks are committed/released *before* initiating the external SMTP network call to prevent database connection exhaustion.
5. **Stale Delivery Recovery**: Any delivery in `SENDING` state older than 10 minutes without a confirmed outbound audit record in the `emails` table is marked `UNCERTAIN`. It cannot be automatically retried, preventing duplicate customer sends.

---

## 5. Complete Alembic Migration History

| Revision ID | Description | Key Changes |
|---|---|---|
| `001_create_users_table` | User identities | `users` table with email, hashed password, active status. |
| `002_create_companies_and_memberships` | Multi-tenancy | `companies` and `company_memberships` (`OWNER`, `ADMIN`, `MEMBER`). |
| `003_create_email_accounts_and_access` | Mail accounts | `email_accounts` with Fernet-encrypted credentials and daily limit counters. |
| `004_create_emails_table` | Mail storage | `emails` table storing headers, subject, body, status. |
| `005_add_imap_fields` | IMAP sync | Added `uid`, `folder`, `flags` to `emails`. |
| `006_create_email_threads` | Threading | `email_threads` table with subject hash and last message timestamp. |
| `007_add_email_mailbox_fields` | Mailbox operations | Added `is_read`, `is_archived`, `is_starred`, `is_trash`. |
| `008_create_email_templates` | Templates | `email_templates` for reusable HTML/text designs. |
| `009_create_email_signatures` | Signatures | `email_signatures` supporting rich HTML signatures. |
| `010_unique_default_signature` | Signature integrity | Partial unique index: at most one default signature per user/account. |
| `011_create_email_attachments` | Attachments | `email_attachments` with file storage path, MIME type, size. |
| `012_create_company_invitations` | Team onboarding | `company_invitations` with secure acceptance tokens and expiration. |
| `013_create_domains_table` | Custom domains | `domains` table for tracking DNS verification records. |
| `014_add_domain_id_to_email_accounts` | Domain link | Foreign key linking `email_accounts.domain_id` to `domains.id`. |
| `015_create_campaigns_tables` | Campaigns foundation | Created `campaigns`, `campaign_steps`, `campaign_recipients`, `campaign_deliveries`, `suppression_list`. |
| `016_create_campaign_attachments` | Campaign files | Added `campaign_attachments` linking campaign emails to uploaded files. |
| `017_campaign_send_interval` | Campaign pacing | Added `send_interval_seconds` and `next_send_at` to `campaigns`. |
| `018_campaign_steps_hardening` | Sequence integrity | Added `uq_campaign_step_number` and `uq_campaign_delivery_recipient_step` constraints; added `stopped_reason`, `retry_count`, `last_error` to recipients. |
| `019_add_source_attachment_id` | Attachment reuse | Added `source_attachment_id` to `email_attachments` for deduplicated copy-on-forward/reply. |

*Verified Head*: `019_add_source_attachment_id` matches both migration files and the active PostgreSQL database instance.

---

## 6. Campaign and Follow-Up Execution Pipeline

```
[Campaign Created with Steps 1..N]
                 |
                 v
[Preflight Validation Passed] ---> [Campaign Launched (RUNNING)]
                 |
                 v
[Initial Step 1 Dispatched to Recipients]
                 |
                 +---> [Delivery Successful]
                 |            |
                 |            v
                 |     [Calculate next_step_due_at = sent_at + step.delay_hours]
                 |     [Recipient Status: SCHEDULED, current_step_number: 1]
                 |
                 v
   [Celery Beat Worker (Every 60s)]
                 |
                 v
[Query due recipients: next_step_due_at <= now() AND campaign.status IN ('RUNNING','COMPLETED')]
                 |
                 v
[Row Lock with SKIP LOCKED]
                 |
                 +---> [Recipient stopped / replied / bounced / unsubscribed?]
                 |            |
                 |            +--> YES: Skip send, clear next_step_due_at
                 |            +--> NO:  Continue
                 |
                 v
[Query previous step delivery for thread_id & message_id]
                 |
                 v
[Send Follow-Up Step N via SMTP with In-Reply-To & References]
                 |
                 +---> [SMTP Success]
                 |            |
                 |            v
                 |     [Record CampaignDelivery(step_id=N, status='SENT')]
                 |     [More steps remain?]
                 |            +--> YES: Advance next_step_due_at for Step N+1
                 |            +--> NO:  Recipient Status = COMPLETED
                 |
                 +---> [SMTP Failure / Timeout]
                              |
                              v
                       [Reconcile stale delivery]
                       [If no email record -> UNCERTAIN, block retry]
```

---

## 7. Capability Audit Matrix

| # | Feature / Capability | Status | Source Location | Test Evidence | Gaps & Production Concerns |
|---|---|:---:|---|---|---|
| **1** | **Multi-step sequence creation & editing** | **COMPLETE** | [`schemas.py:CampaignStepWrite`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/schemas.py#L80)<br>[`CampaignContentStep.tsx`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/frontend/src/components/campaigns/CampaignContentStep.tsx#L120) | `test_followup_hardening.py::test_followup_steps_create_and_update_sync` | Frontend wizard limits to 3 follow-ups; backend supports up to 10. |
| **2** | **Step 1 synchronization with campaign root** | **COMPLETE** | [`service.py:create_campaign`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/service.py#L180)<br>[`delivery_service.py:1546`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/delivery_service.py#L1546) | `test_followup_hardening.py::test_campaign_creation_and_update_authoritatively_syncs_step_1` | Modifying Step 1 properly syncs root `campaign.subject` and body. |
| **3** | **Per-step delays & scheduling persistence** | **COMPLETE** | [`models.py:CampaignStep.delay_hours`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/models.py#L196)<br>[`recipient.next_step_due_at`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/models.py#L250) | `test_followup_hardening.py::test_followup_scheduling_and_threaded_dispatch` | Granularity is whole hours (1–720 hrs). |
| **4** | **Celery Beat scheduling & periodic polling** | **COMPLETE** | [`celery_app.py:30`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/workers/celery_app.py#L30)<br>[`campaign_tasks.py:78`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/workers/campaign_tasks.py#L78) | Beat registers `scheduled-campaign-dispatch-periodic` running every 60s. | Polling interval is hard-coded at 60s. |
| **5** | **Follow-ups sent in correct email thread** | **COMPLETE** | [`delivery_service.py:1558-1575`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/delivery_service.py#L1558)<br>[`EmailSendRequest.in_reply_to`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/emails/schemas.py#L150) | `test_followup_hardening.py::test_followup_scheduling_and_threaded_dispatch` | Pulls `message_id` from step N-1 delivery; populates `In-Reply-To` and `References`. |
| **6** | **Genuine reply detection & attribution** | **COMPLETE** | [`monitoring_service.py:146`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/emails/monitoring_service.py#L146)<br>[`is_genuine_reply`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/emails/monitoring_service.py#L48) | `test_followup_hardening.py::test_followup_auto_stop_on_genuine_reply` | Filters out bounces and auto-replies (`Auto-Submitted`, `X-Autoreply`). Scoped by `company_id`. |
| **7** | **Automatic stopping after replies** | **COMPLETE** | [`monitoring_service.py:215`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/emails/monitoring_service.py#L215) | `test_followup_hardening.py::test_followup_auto_stop_on_genuine_reply` | Sets `recipient.status = STOPPED`, `stopped_reason = 'REPLIED'`, clears `next_step_due_at`. |
| **8** | **Bounce, unsubscribe & suppression handling** | **COMPLETE** | [`delivery_service.py:1506-1530`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/delivery_service.py#L1506)<br>[`public_routes.py`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/public_routes.py) | `test_followup_hardening.py::test_followup_skip_on_unsubscribe_or_bounce` | Unsubscribed or bounced recipients are stopped immediately and added to `suppression_list`. |
| **9** | **Pause, resume & cancellation safety** | **COMPLETE** | [`delivery_service.py:1460`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/delivery_service.py#L1460)<br>[`cancel_campaign`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/delivery_service.py#L650) | `test_followup_hardening.py::test_campaign_cancellation_safely_stops_recipients_without_reactivation` | Paused campaigns are excluded from due polling; cancelled campaigns set `stopped_reason='CAMPAIGN_CANCELLED'`. |
| **10** | **Per-recipient stop, skip & reschedule controls** | **MISSING** | Missing in commit `a0f4810`. (Exists only in `stash@{0}`). | No active tests on `master`. | Operators cannot manually stop, skip, or reschedule an individual recipient in an active campaign. |
| **11** | **SMTP retries & stale delivery reconciliation** | **COMPLETE** | [`delivery_service.py:1364`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/delivery_service.py#L1364)<br>[`uq_campaign_delivery_recipient_step`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/models.py#L278) | `test_followup_hardening.py::test_stale_delivery_without_audit_record_becomes_uncertain` | Reconciles stuck `SENDING` deliveries >10 mins without audit log into `UNCERTAIN`, preventing double-sends. |
| **12** | **Worker concurrency & row-level locking** | **COMPLETE** | [`delivery_service.py:1484`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/delivery_service.py#L1484)<br>`with_for_update(skip_locked=True)` | `test_followup_hardening.py::test_delivery_unique_constraint_on_campaign_recipient_and_step` | Prevents multi-worker collision; lock released before network transmission. |
| **13** | **Account-level sending limits & pacing** | **PARTIAL** | [`campaign.send_interval_seconds`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/models.py#L112) | Verified for Step 1 pacing | Follow-up steps process up to 50 due recipients per batch without cross-campaign account throttle. |
| **14** | **Sending windows, timezones & weekdays** | **MISSING** | Missing in commit `a0f4810`. (Exists in `stash@{0}`). | No active tests on `master`. | Emails dispatch immediately when `delay_hours` expire, including nights and weekends. |
| **15** | **Merge-field validation & step preview** | **PARTIAL** | [`render_content_for_recipient`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/modules/campaigns/delivery_service.py#L1550) | `tests/test_merge_fields.py` | Variables replaced at render time, but no interactive preview modal exists for follow-up steps. |
| **16** | **Test-send behavior isolated from records** | **MISSING** | Missing in commit `a0f4810`. (Exists in `stash@{0}`). | No active tests on `master`. | No API route to send a single test email for Step N to the user's inbox without affecting analytics. |
| **17** | **Step-level analytics & metrics accuracy** | **MISSING** | [`CampaignDetailPage.tsx`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/frontend/src/pages/CampaignDetailPage.tsx#L380) | Only aggregated totals verified | Only shows campaign aggregate stats (`followup_sent_count`, `followup_replied_count`). No step funnel table. |
| **18** | **Company authorization & tenant isolation** | **COMPLETE** | [`get_company_membership`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/backend/app/core/auth.py)<br>All campaign routes join on `company_id`. | `tests/test_campaign_auth.py` | Strict tenant validation; foreign resources return `404 Not Found`. |
| **19** | **Database constraints & migration consistency** | **COMPLETE** | Migrations `015` through `019`. Constraints: `uq_campaign_step_number`, `uq_campaign_delivery_recipient_step`. | Clean database migration head `019`. | Schema is fully consistent with SQLAlchemy ORM models. |
| **20** | **Frontend usability & sequence controls** | **PARTIAL** | [`CampaignContentStep.tsx`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/frontend/src/components/campaigns/CampaignContentStep.tsx)<br>[`CampaignReviewStep.tsx`](file:///c:/Users/dipak/Documents/projects/Email_Monitoring/frontend/src/components/campaigns/CampaignReviewStep.tsx) | `campaignWizard.test.tsx` (25/25)<br>`campaignWizardC122.test.tsx` (13/13) | Sequence builder works well for up to 3 follow-ups, but lacks per-recipient controls and step test send. |

---

## 8. Development Workflow Rules & Constraints

Antigravity operates under an established, structured engineering protocol:

1. **Stitch AI Design → Design Review → Antigravity Implementation → Report Review → Manual Verification → Separate Git Commit**:
   - Never commit automatically or push directly to remote.
   - Implement only the smallest justified change for each milestone.
   - Present a concise, factual implementation report after finishing code edits.
   - Wait for explicit user authorization before generating git commit commands.
2. **Strict Non-Destructive Principles**:
   - Never execute `git reset --hard`, `git clean -fd`, `git stash drop`, or switch branches without explicit consent.
   - Never run destructive Docker commands (`docker compose down -v`).
   - Never send real emails over external SMTP networks or modify live email account credentials.
   - Do not add unapproved heavy third-party dependencies.
   - Preserve all existing uncommitted and untracked files.

---

## 9. Security, Reliability & Technical Debt Findings

### Ranked Severity:
- **P0: Domain Reputation Risk (Missing Sending Windows)**:
  - *Evidence*: `delivery_service.py:process_due_followup_steps` checks solely whether `next_step_due_at <= now()`.
  - *Risk*: A 24-hour follow-up sent on Friday afternoon will fire on Saturday afternoon; an email sent at 11:00 PM will follow up at 11:00 PM. High spam complaints and domain blacklisting risk.
- **P1: Operational Control Gap (Missing Per-Recipient Controls)**:
  - *Evidence*: `backend/app/modules/campaigns/routes.py` has no endpoints to pause, skip, or stop a single recipient.
  - *Risk*: If a prospect phones an account executive asking to stop emails, operators must cancel the entire campaign or edit database rows manually.
- **P1: Lack of Sandbox Verification (Missing Step Test-Send)**:
  - *Evidence*: No route exists to test-fire Step 2 or Step 3.
  - *Risk*: Broken merge tags or malformed HTML in follow-ups are discovered only after live delivery to real clients.
- **P2: Batch Volume Spike on Due Follow-Ups**:
  - *Evidence*: Up to 50 recipients are dispatched per cycle without checking email account daily limits.
  - *Risk*: Potential 550 SMTP provider rate-limit errors during high-volume spikes.

---

## 10. Prioritized Next-Step Roadmap

| Milestone | Objective | Scope & Target Files |
|---|---|---|
| **Milestone 1 (Recommended Next)** | **Per-Recipient Operational Controls** | Add API routes (`/recipients/{id}/stop`, `/recipients/{id}/skip`, `/recipients/{id}/reschedule`) and UI action dropdowns in `RecipientTable.tsx`. (Source already drafted in `stash@{0}`). |
| **Milestone 2** | **Step-Level Test Sends & Content Previews** | Add `POST /campaigns/{id}/steps/{step_id}/test-send` sending isolated preview emails to authenticated user; add UI test modal in `CampaignContentStep.tsx`. |
| **Milestone 3** | **Sending Windows & Timezone Governance** | Create migration `020` for `timezone`, `send_window_start`, `send_window_end`, `send_days`; integrate window projection in `delivery_service.py`. |
| **Milestone 4** | **Step-Level Analytics Funnel** | Implement `GET /campaigns/{id}/steps/analytics` returning per-step conversion funnel; add visual funnel card in `CampaignDetailPage.tsx`. |

---

## 11. Testing & Verification Run Evidence

The following verification commands were executed directly against the active environment:

1. **Backend Follow-Up Sequence Hardening Suite**:
   ```bash
   docker compose exec -T backend pytest tests/test_followup_hardening.py -v
   ```
   - **Result**: `10 passed in 41.25s` (100% pass rate).
   - **Verified**: Stale delivery reconciliation to `UNCERTAIN`, duplicate retry blocking, campaign cancellation stopping recipients, Step 1 sync, composite unique constraints, multi-step dispatch and threading, genuine reply auto-stop, and bounce/unsubscribe skipping.
2. **Frontend Campaign Wizard Suite**:
   ```bash
   npm run test -- --run src/components/campaigns/__tests__/campaignWizard.test.tsx
   ```
   - **Result**: `25 passed (25)` in 48.65s.
3. **Frontend Signature & Composer Defaults Suite**:
   ```bash
   npm run test -- --run src/components/campaigns/__tests__/campaignWizardC122.test.tsx
   ```
   - **Result**: `13 passed (13)` in 9.57s.
4. **Frontend Campaign Suppressions Suite**:
   ```bash
   npm run test -- --run src/components/campaigns/__tests__/campaignSuppressions.test.tsx
   ```
   - **Result**: `11 passed (11)` in 9.01s.
5. **Frontend Campaign Detail & Navigation Suite**:
   ```bash
   npm run test -- --run src/components/campaigns/__tests__/campaignDetailAndNavigation.test.tsx
   ```
   - **Result**: `25 passed (25)` in 18.27s.
6. **Frontend Campaign Recipients Lifecycle Suite**:
   ```bash
   npm run test -- --run src/components/campaigns/__tests__/campaignRecipients.test.tsx
   ```
   - **Result**: `17 passed (17)` in 8.32s.
7. **Database Migration State Check**:
   ```bash
   docker compose exec -T backend alembic current
   ```
   - **Result**: `019_add_source_attachment_id (head)` (PostgreSQL transactional DDL confirmed).
