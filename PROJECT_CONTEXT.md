# Email Monitoring System (PulseMail) — Master Project Context

> **Authoritative Context Document for Antigravity AI Assistants and Developers**  
> **Last Updated:** October 1, 2026  
> **Repository Path:** `C:\Users\dipak\Documents\projects\Email_Monitoring`  
> **Target Audience:** Any new or resumed Antigravity session working on this codebase.  
> **Purpose:** Provide complete, standalone context in a single file so any new session can understand, develop, test, and maintain the system without losing prior architectural decisions or regressing historical fixes.

---

## Table of Contents

1. [Project Identity & Purpose](#1-project-identity--purpose)
2. [Technology Stack](#2-technology-stack)
3. [System Architecture & Container Topology](#3-system-architecture--container-topology)
4. [Multi-Tenancy & Authorization Model](#4-multi-tenancy--authorization-model)
5. [Database Architecture & Data Models](#5-database-architecture--data-models)
6. [Email Sending (SMTP) & MIME Pipeline](#6-email-sending-smtp--mime-pipeline)
7. [Email Synchronization (IMAP) & Background Sync](#7-email-synchronization-imap--background-sync)
8. [Conversation Threading Engine](#8-conversation-threading-engine)
9. [Mailbox Architecture & UI](#9-mailbox-architecture--ui)
10. [Draft System & Automatic Autosave Architecture](#10-draft-system--automatic-autosave-architecture)
11. [Email Templates Management & CSS Inlining](#11-email-templates-management--css-inlining)
12. [Email Signatures Module & Compose Integration](#12-email-signatures-module--compose-integration)
13. [Attachments Lifecycle](#13-attachments-lifecycle)
14. [Celery & Redis Background Worker Infrastructure](#14-celery--redis-background-worker-infrastructure)
15. [Docker & Local Infrastructure Rules](#15-docker--local-infrastructure-rules)
16. [Backend Codebase Structure](#16-backend-codebase-structure)
17. [Frontend Codebase Structure](#17-frontend-codebase-structure)
18. [Historical Milestones & Recent Commits](#18-historical-milestones--recent-commits)
19. [Critical Historical Bug Fixes (Never Regress)](#19-critical-historical-bug-fixes-never-regress)
20. [Testing & Verification Conventions](#20-testing--verification-conventions)
21. [Mandatory Development Rules for AI Agents](#21-mandatory-development-rules-for-ai-agents)
22. [Protocol for Executing Tasks in New Chats](#22-protocol-for-executing-tasks-in-new-chats)
23. [Authoritative File Index](#23-authoritative-file-index)

---

## 1. Project Identity & Purpose

### 1.1 Technical Identity
- **Project Technical Name:** `Email Monitoring System`
- **Frontend / Product Display Name:** `PulseMail` (used in web navigation, sidebar headers, browser titles, and UI branding).
- **Core Purpose:** A high-reliability, multi-tenant email monitoring, dispatch, tracking, and synchronization platform. Built as a standalone platform while maintaining strict modularity to allow seamless future integration into an ERP (Enterprise Resource Planning) system without refactoring core email tables, routing, or services.
- **Inspiration Note:** Brevo is referenced **exclusively as visual UI/UX layout inspiration**. Brevo is **NOT** a vendor, API provider, dependency, or external integration of this codebase. The system operates directly against standard RFC-compliant SMTP and IMAP servers.

---

## 2. Technology Stack

### 2.1 Backend
- **Language / Runtime:** Python 3.12 (running on Linux inside Docker container `email_monitoring_backend`, or native virtualenv).
- **Web Framework:** FastAPI (async routing with Pydantic v2 schemas and validation).
- **ORM / Database Layer:** SQLAlchemy 2.x using `AsyncSession` with `asyncpg` for web requests and dedicated sync/async sessions with `NullPool` for Celery worker processes.
- **Database Engine:** PostgreSQL 16 Alpine (`email_monitoring_db` in Docker).
- **Schema Migrations:** Alembic (`backend/alembic/`).
- **Cache & Queue:** Redis 7 Alpine (`email_monitoring_redis` in Docker).
- **Asynchronous Task Queue:** Celery 5.x with Celery Beat periodic scheduler.
- **Email Protocols:**
  - Outgoing: Python standard library `smtplib` / `email` modules wrapped in custom async-safe executors with SSL/STARTTLS support and AES-encrypted credential storage.
  - Incoming: `imaplib` with specialized RFC-822/RFC-2822 email parsers and MIME multipart extractors.
- **HTML Inlining & Sanitization:** `premailer` for robust CSS-to-inline-style transformation for HTML emails, and custom sanitization for secure rendering.
- **Cryptography:** Fernet symmetric authenticated encryption for SMTP/IMAP credentials at rest.

### 2.2 Frontend
- **Framework:** React 18.3+ with TypeScript 5.6+.
- **Build Tool / Bundler:** Vite 5.4+ (`@vitejs/plugin-react`).
- **Styling:** Tailwind CSS 3.4+ with custom utility tokens, modern subtle borders, Precision Indigo design language, and zero intrusive fixed positioning.
- **Icons:** `lucide-react`.
- **State Management & Data Fetching:** `@tanstack/react-query` (v5) with custom cache invalidation hooks.
- **Routing:** `react-router-dom` (v6).
- **Rich Text Editing:** Custom contenteditable HTML editor with font family, header levels, blockquotes, alignment, lists, and safe HTML sanitization (`dompurify`).

### 2.3 Container & Infrastructure
- **Container Orchestrator:** Docker Compose (`docker-compose.yml`).
- **Containers:**
  1. `email_monitoring_db` (Postgres 16 Alpine on internal port 5432, host port mapped to 5432 or 5433).
  2. `email_monitoring_redis` (Redis 7 Alpine on internal/host port 6379).
  3. `email_monitoring_backend` (FastAPI Uvicorn app on port 8000).
  4. `email_monitoring_worker` (Celery worker).
  5. `email_monitoring_beat` (Celery beat periodic sync dispatcher).
  6. `email_monitoring_frontend` (Production Nginx Alpine image serving built Vite bundle on port 5173).

---

## 3. System Architecture & Container Topology

```
┌────────────────────────────────────────────────────────┐
│             React + TypeScript SPA (PulseMail)         │
│             Served via Nginx / Vite on Port 5173       │
└───────────────────────────┬────────────────────────────┘
                            │ HTTP JSON API (Bearer JWT)
                            ▼
┌────────────────────────────────────────────────────────┐
│              FastAPI Backend (Port 8000)               │
│  - Routes (Thin presentation & parameter validation)   │
│  - Dependencies (Auth, Company scope, Account access)  │
│  - Services (Draft, Mailbox, Threads, Templates, Sigs) │
└──────────────┬────────────────────────────┬────────────┘
               │                            │
               ▼ Async SQLAlchemy           ▼
┌──────────────────────────────┐ ┌───────────────────────┐
│ PostgreSQL 16 (Port 5432)   │ │ Redis 7 (Port 6379)   │
│ - Multi-tenant Isolation     │ │ - Celery Message Broker│
│ - Emails, Threads, Drafts    │ │ - Result Backend      │
└──────────────────────────────┘ └──────────┬────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │ Celery Worker & Beat    │
                               │ - Periodic IMAP Sync    │
                               │ - Retry handling        │
                               └────────────┬────────────┘
                                            │
               ┌────────────────────────────┴────────────┐
               ▼                                         ▼
┌──────────────────────────────┐       ┌─────────────────────────┐
│ Outgoing SMTP Dispatcher     │       │ Incoming IMAP Collector │
│ - Google, Yahoo, Zoho, Custom│       │ - UID tracking          │
│ - STARTTLS / SSL             │       │ - Auto-reply detection  │
│ - CSS Inlining (premailer)   │       │ - Thread reconciliation │
│ - Duplicate-Safe Signatures  │       │ - Multipart attachments │
└──────────────────────────────┘       └─────────────────────────┘
```

### 3.1 Architectural Principles
1. **Thin Routes, Fat Services:** Route handlers only parse request parameters, execute authorization dependencies, and return Pydantic models. All database transactions, provider interactions, and state transitions belong exclusively in `app/modules/<module>/<name>_service.py`.
2. **Strict Protocol Isolation:** Low-level SMTP and IMAP socket handling is isolated in `app/services/smtp/` and `app/services/imap/`. Services never speak raw protocol commands directly.
3. **Auditability & Traceability:** Emails and drafts are never deleted from the database during ordinary operations; they are soft-deleted via `is_deleted = True` and timestamped with `deleted_at`.

---

## 4. Multi-Tenancy & Authorization Model

### 4.1 Tenancy Hierarchy
```
Company (Tenant Organization)
  ├── CompanyUser (Role: OWNER | ADMIN | MEMBER)
  │     └── Associated with User (Global Login Identity)
  │
  └── EmailAccount (e.g. sales@company.com, support@company.com)
        ├── SMTP & IMAP Credentials (AES Fernet Encrypted)
        ├── EmailAccountAccess (Explicit authorization per User)
        ├── Emails (status: DRAFT, SENT, RECEIVED, BOUNCED, etc.)
        ├── EmailThreads (Conversation grouping)
        ├── EmailTemplates (Company-wide or Account-specific)
        └── EmailSignatures (Account-specific with Default flag)
```

### 4.2 Core Authorization Invariants
1. **User Identity != Email Account:** A `User` represents an individual logging in via email/password. A `User` does not own an inbox directly; companies own `EmailAccount` records.
2. **Access Rights Hierarchy:**
   - **Company Isolation:** Users can only access resources belonging to a company where they hold an active `CompanyUser` membership.
   - **Role Privileges:**
     - `OWNER` / `ADMIN`: Granted administrative authority over the company, can manage users, templates, and view/configure accounts.
     - `MEMBER`: Regular team member; requires an explicit `EmailAccountAccess` row to read, draft, or send from a specific `EmailAccount`.
   - **Account Authorization Method:** Verified on the backend via `EmailAccountService.check_user_access(db, account, user_id, user_role)`.
3. **CRITICAL GOTCHA: `CompanyService.get_user_companies()` Return Contract:**
   - `CompanyService.get_user_companies()` returns `List[Tuple[Company, str]]`, where the second element is the role string (e.g., `'OWNER'`, `'ADMIN'`, `'MEMBER'`), **NOT** a `CompanyUser` model instance!
   - Do **NOT** call `.role` on the second element; pass it directly as `user_role=comp_user`.
4. **Zero Compromise Security:** Backend routes must never bypass company or account authorization checks to make frontend interactions "easier".

---

## 5. Database Architecture & Data Models

All models reside under `backend/app/modules/` and inherit from `app.core.database.Base`.

### 5.1 Entities Summary

| Model | Table | Location | Description |
| :--- | :--- | :--- | :--- |
| `User` | `users` | `app/modules/auth/models.py` | System user with hashed password, superuser status, and company links. |
| `Company` | `companies` | `app/modules/companies/models.py` | Tenant boundary owning accounts, emails, templates, and signatures. |
| `CompanyUser` | `company_users` | `app/modules/companies/models.py` | Maps `User` to `Company` with role (`OWNER`, `ADMIN`, `MEMBER`). |
| `EmailAccount` | `email_accounts` | `app/modules/email_accounts/models.py` | Company email account with encrypted SMTP/IMAP hosts, ports, and credentials. |
| `EmailAccountAccess` | `email_account_access` | `app/modules/email_accounts/models.py` | Authorizes specific `User` IDs to use an `EmailAccount`. |
| `Email` | `emails` | `app/modules/emails/models.py` | Core unified model for ALL outgoing, incoming, and draft emails. |
| `EmailThread` | `email_threads` | `app/modules/emails/models.py` | Conversation thread linking related message records together. |
| `EmailTemplate` | `email_templates` | `app/modules/emails/models.py` | Reusable email subject/body content per company/account. |
| `EmailSignature` | `email_signatures` | `app/modules/emails/models.py` | Outgoing formatted signatures per account with unique default flag. |
| `EmailAttachment` | `email_attachments` | `app/modules/emails/models.py` | File metadata and disk storage pointers linked to an `Email`. |

### 5.2 The Unified `Email` Model
Drafts, sent messages, received messages, and bounces use the **same single table (`emails`)**. Do **NOT** create a separate table for drafts.

Key fields of `emails`:
- `id` (Integer, Primary Key)
- `company_id` (ForeignKey `companies.id`, CASCADE)
- `email_account_id` (ForeignKey `email_accounts.id`, CASCADE)
- `user_id` (ForeignKey `users.id`, SET NULL) — The user who drafted or sent the message.
- `thread_id` (ForeignKey `email_threads.id`, CASCADE) — Assigned conversation thread.
- `message_id` (String(255), nullable) — RFC 2822 `Message-ID`.
- `imap_uid` (String(255), nullable) — Unique IMAP UID for incoming messages.
- `in_reply_to` (String(255), nullable) — Message-ID of the parent message being replied to.
- `references_header` (Text, nullable) — Full chain of ancestor Message-IDs.
- `direction` (String(50)) — `OUTGOING` or `INCOMING`.
- `status` (String(50)) — `DRAFT`, `QUEUED`, `SENDING`, `SENT`, `FAILED`, `BOUNCED`, `RECEIVED`.
- `sender` (String(255)) — Formatted From address (e.g., `Dipak <dipak@company.com>`).
- `recipients` (JSON) — Array of destination email strings `["user@example.com"]`.
- `cc`, `bcc` (JSON, nullable) — Array of CC/BCC email strings.
- `subject` (String(998)) — Email subject line.
- `body_text`, `body_html` (Text, nullable) — Plain text and formatted HTML email content.
- `is_read` (Boolean, default True for drafts/sent, dynamic for incoming).
- `is_starred` (Boolean, default False).
- `is_deleted` (Boolean, default False) — Soft-delete flag.
- `deleted_at` (DateTime, nullable) — Soft-deletion timestamp.
- `sent_at`, `received_at` (DateTime, nullable) — Dispatch or ingestion timestamps.
- `error_message` (Text, nullable) — Sanitized error message if sending failed or bounced.

---

## 6. Email Sending (SMTP) & MIME Pipeline

### 6.1 Dispatch Architecture
1. **Protocol Implementation:** Custom `SMTPClient` using Python `smtplib` inside asyncio executors to avoid blocking the event loop.
2. **Security:** Supports `STARTTLS` (typically port 587) and `SSL` (port 465).
3. **Flow:**
   ```
   Compose UI ──► POST /api/v1/emails/drafts/{id}/send ──► EmailDraftService.send_draft()
     ├─► Row Lock: SELECT ... FOR UPDATE (prevents double-sending race condition)
     ├─► Verification: Validates sender account authorization & recipients
     ├─► CSS Inlining: Premailer transforms <style> blocks into inline CSS attributes
     ├─► Signature Application: If not already present, attaches effective signature
     ├─► Message Assembly: MIME multipart/alternative with inline attachments
     ├─► Thread Reconciliation: Updates thread message_count & last_message_at
     ├─► SMTP Dispatch: smtplib connects, authenticates, and transmits
     └─► Status Update: Sets status = 'SENT', sent_at = now(), clears draft status
   ```

### 6.2 CSS Inlining Engine
- Email clients (Gmail, Outlook, Apple Mail) often strip `<style>` tags in `<head>`.
- To preserve rich layouts, colors, centered cards, and borders from templates:
  - `template_service.py` / `draft_service.py` runs HTML through `premailer` before final MIME packaging.
  - This ensures received emails render with complete typography, button styling, and layout fidelity identical to the Compose preview.

---

## 7. Email Synchronization (IMAP) & Background Sync

1. **Protocol Implementation:** Custom `IMAPClient` supporting SSL/STARTTLS and UID-based message fetching.
2. **Duplicate Prevention:** Unique constraint on `(email_account_id, imap_uid)` guarantees incoming messages are never stored twice.
3. **Auto-Reply & Bounce Detection:** Incoming headers (`Auto-Submitted`, `X-Autoreply`, `Content-Type: multipart/report`) are analyzed to classify incoming messages into `RECEIVED` vs `BOUNCED`.
4. **Thread Matching:** Checks incoming `In-Reply-To` and `References` headers against existing database `message_id` records to automatically attach incoming replies to their existing `EmailThread`.
5. **Periodic Execution:** Executed every 5 minutes by `Celery Beat` via `sync_all_active_accounts_task`.

---

## 8. Conversation Threading Engine

### 8.1 Association Algorithm
1. **Outgoing Message:** When an email or draft is created with an explicit `thread_id` and `in_reply_to`, it is linked to that thread.
2. **Incoming Message:**
   - Step 1: Look up parent email where `Email.message_id == incoming.in_reply_to`. If found, join that email's `thread_id`.
   - Step 2: If no direct parent matches `in_reply_to`, parse the `References` header and look for any known `message_id` in the account.
   - Step 3: If no ancestor matches, normalize the subject (strip `Re:`, `Fwd:`, `re:`, `[FWD]`) and find any thread in the account with identical normalized subject and active participants.
   - Step 4: If no match exists, generate a new `EmailThread`.
3. **Multi-Turn Threading Invariant:** In multi-turn threads (Customer replies to a reply), the system extracts all message IDs across the entire References chain. Replying to a reply **MUST NEVER** split the conversation into a second thread.

---

## 9. Mailbox Architecture & UI

### 9.1 Mailbox Folders
1. **Inbox:** `direction == 'INCOMING'`, `status == 'RECEIVED'`, `is_deleted == False`.
2. **Sent:** `direction == 'OUTGOING'`, `status == 'SENT'`, `is_deleted == False`.
3. **Drafts:** `status == 'DRAFT'`, `is_deleted == False`.
4. **Responses:** Incoming genuine customer replies with `has_reply == True`.
5. **Bounced:** `status == 'BOUNCED'`, `is_deleted == False`.
6. **Trash:** `is_deleted == True` (soft-deleted records across all folders).

### 9.2 Mailbox Toolbar & Pagination
- **Gmail-Style Single-Row Responsive Layout:** `MailboxToolbar.tsx` contains:
  - **Left:** Select All checkbox + **Conditional Bulk Actions** (Star, Mark Read/Unread, Move to Trash). Actions are hidden when 0 emails are selected and appear dynamically when $\ge 1$ email is selected.
  - **Center:** Account selector, Sort dropdown, and a flexible Search bar.
  - **Right:** Page size selector (`25`, `50`, `100`, `200`, default `50`), count range (`1–50 of 3,680`), and compact `<` `>` pagination controls.
- **Pagination Safety:** `MailboxPage.tsx` uses `placeholderData: keepPreviousData` to prevent component unmounting or resetting to page 1 during query fetching.

---

## 10. Draft System & Automatic Autosave Architecture

### 10.1 Background Draft Architecture
- Drafts are stored in the `emails` table with `status = 'DRAFT'`.
- Backend endpoints:
  - `POST /api/v1/emails/drafts`: Create work-in-progress draft.
  - `PUT /api/v1/emails/drafts/{id}`: Update draft with latest partial content.
  - `POST /api/v1/emails/drafts/{id}/send`: Send existing draft via SMTP.
  - `DELETE /api/v1/emails/drafts/{id}`: Discard (soft-delete) draft.
  - `POST /api/v1/emails/drafts/{id}/attachments`: Add attachment directly to draft.

### 10.2 Automatic Draft Saving Workflow
The manual "Save as Draft" button is permanently removed. Compose operates like modern Gmail:
1. **Initial Mount:** Opening `/compose` with an empty form does **NOT** trigger draft creation.
2. **Meaningful Change Detection:** Any edit to To, CC, BCC, Subject, Body, Signature, Template, or Attachments marks the form dirty.
3. **Debounced Autosave (900ms):** Edits reset a 900ms timer. When the user pauses typing for 900ms:
   - If `draftId` is `null`: calls `emailsApi.createDraft()`, saves returned ID in `draftIdRef.current` and state.
   - If `draftId` exists: calls `emailsApi.updateDraft(draftId, payload)`.
4. **Race Condition Prevention & Serialization:**
   - `isSavingRef.current`: Ensures only ONE save request is in flight at any time.
   - `pendingSaveRef.current`: If the user continues typing while an HTTP save request is in flight, the pending save flag is raised. Once the in-flight request finishes, `performSave` immediately triggers another save with the latest synchronous state.
   - `latestStateRef.current`: Synchronously updated in all input handlers so that save requests never read stale React state.
5. **Send / Autosave Interaction:**
   - Clicking "Send Message" immediately marks `isSending = true`, cancels any running autosave timer, and awaits any in-flight save.
   - Persists the final state to the existing draft, then calls `emailsApi.sendDraft(draftId)`.
   - On send success, the draft transitions to `SENT` in the database, disappears from Drafts, and the page navigates to `/mailbox?folder=sent`.
   - If send fails, `isSending` resets to `false`, leaving the draft intact so the user can fix the issue.
6. **Back Navigation Protection:**
   - Clicking "Back to Mailbox" flushes any unsaved changes immediately before routing to `/mailbox`.
7. **Draft Reopening:**
   - Both `EmailDetailDrawer.tsx` and `EmailDetailPage.tsx` display a **"Continue Editing Draft"** button when `email.status === "DRAFT"`, directing to `/compose?draft_id={id}`.
   - `ComposePage.tsx` loads the existing draft, sets `draftId`, restores subject, body, recipients, thread references, attachments, and effective signature.

---

## 11. Email Templates Management & CSS Inlining

### 11.1 Template Architecture
- Templates live in `email_templates` table (`id`, `company_id`, `email_account_id`, `name`, `subject`, `body_html`, `body_text`, `is_active`, `created_at`, `updated_at`).
- Account-scoped templates (`email_account_id != null`) or company-wide templates (`email_account_id == null`).
- Inactive templates (`is_active = False`) are **filtered out** from Compose's "Insert Template" picker.
- React Query cache invalidation hook: `["templates", selectedAccountId, "active"]` is automatically refetched on template create, activate, deactivate, or delete.

### 11.2 Compose Template Integration
- Selecting a template replaces or appends subject and body.
- When an email using a template is sent, the full HTML body is preserved through Compose `bodyHtml` -> draft `body_html` -> send draft -> `premailer` CSS inliner -> MIME multipart message.

---

## 12. Email Signatures Module & Compose Integration

### 12.1 Signature Architecture
- Model: `EmailSignature` (`id`, `company_id`, `email_account_id`, `name`, `body_text`, `body_html`, `is_default`, `created_at`, `updated_at`).
- Each email account can designate one signature as its `is_default = True`.

### 12.2 Signature Management UI (`SignaturesPage.tsx`)
- Inspired by modern Stitch design:
  - Account filter dropdown ("All Accounts" or specific account).
  - Status filter dropdown ("All Statuses", "Default only", "Non-default").
  - Search input with clear button.
  - Signature cards displaying account badge, default tag, rich text preview, and quick actions: Set as Default, Edit, Duplicate, Preview, Delete.
  - Slide-over `SignatureDrawer.tsx` for creating/editing with tabbed HTML/plain-text editing, live preview card, and variable helper chips.
  - Preview modal (`SignaturePreviewModal.tsx`) and Delete modal (`DeleteSignatureModal.tsx`).

### 12.3 Compose & Autosave Signature Integration (CRITICAL ARCHITECTURE)
1. **Separation of Concerns:**
   - In `ComposePage.tsx`, the editor state (`bodyHtml`, `bodyText`) represents **only the user's typed email content**.
   - Signatures are **NOT** blindly copied into the editor DOM on every render. This eliminates cursor jumping and duplicate signature accumulation.
   - The effective signature is rendered in a dedicated preview card below the editor with a `[Default]` badge or `[Custom Signature]` badge and a `"Reset to default"` button.
2. **Explicit vs Default Signature Propagation:**
   - **Case A — No Signature Manually Selected:**
     - `selectedSignature` is `null`.
     - React Query loads `defaultSignature` for `selectedAccountId`.
     - In `create_draft()`: `draft_in.signature_id` is `None` → backend resolves `SignatureService.get_default_signature()` and applies it.
     - In `update_draft()`: `draft_update.signature_id` is `None` → backend resolves `SignatureService.get_default_signature()` and applies it.
   - **Case B — Explicit Signature Selected:**
     - User selects a signature via "Insert Signature".
     - `selectedSignature` is set; `signature_id` is passed in draft create, autosave update, and send.
     - In `update_draft()`: validates account ownership and applies the explicit signature, overriding the default signature.
   - **Case C — Account Switching:**
     - Selecting a different account clears `selectedSignature` (`null`).
     - React Query fetches the new account's default signature.
     - The draft update applies the new account's default signature.
   - **Case D — Duplicate Protection:**
     - `SignatureService.apply_signature_to_content()` contains duplicate detection: checks if signature text or HTML substring is already present before appending. Repeated autosaves will **never** duplicate the signature.

---

## 13. Attachments Lifecycle

- **Size Boundary:** Authoritative max attachment size is **25 MB** (`MAX_ATTACHMENT_SIZE_BYTES = 25 * 1024 * 1024`).
- **Direct Upload to Draft:** When the user selects files on `ComposePage`:
  - If no draft exists yet, the draft is created immediately.
  - Files are uploaded directly via `emailsApi.uploadDraftAttachment(draftId, file)`.
  - Stored files are tracked in `serverAttachments` and are **never re-uploaded** on subsequent autosave cycles.
- **Storage:** Stored on the backend in `./uploads/` (mapped to Docker volume `uploads_data`) with unique UUID storage filenames and hashed database records.

---

## 14. Celery & Redis Background Worker Infrastructure

- **Redis URL:** `redis://redis:6379/0` (inside Docker) or `redis://localhost:6379/0` (host).
- **Worker Configuration:** Defined in `backend/app/workers/celery_app.py`.
- **Periodic Sync:** `celery_app.conf.beat_schedule` executes `app.workers.tasks.sync_all_active_accounts_task` every 5 minutes (`SYNC_INTERVAL_MINUTES = 5`).
- **Worker Engine:** `worker_async_engine` in `backend/app/workers/tasks.py` uses `NullPool` to prevent asyncpg cross-event-loop connection reuse issues during Celery task execution.

---

## 15. Docker & Local Infrastructure Rules

### 15.1 Docker Compose Services
- `email_monitoring_db` (Postgres 16 Alpine, volume: `postgres_data`).
- `email_monitoring_redis` (Redis 7 Alpine, volume: `redis_data`).
- `email_monitoring_backend` (FastAPI Uvicorn app, volume: `uploads_data`).
- `email_monitoring_worker` (Celery worker).
- `email_monitoring_beat` (Celery beat periodic scheduler).
- `email_monitoring_frontend` (Nginx Alpine serving production Vite build on port 5173).

### 15.2 CRITICAL INFRASTRUCTURE RULES
1. **Do NOT touch Native Postgres:** The host machine may have a native PostgreSQL 17 installation. **DO NOT** stop, delete, or alter native PostgreSQL services. The application runs exclusively on PostgreSQL 16 inside Docker container `email_monitoring_db`.
2. **Do NOT wipe volumes:** Never execute `docker compose down -v` unless explicitly requested by the user.

---

## 16. Backend Codebase Structure

```
backend/
├── alembic/                      # Database migration scripts
├── app/
│   ├── core/
│   │   ├── config.py             # Settings, pydantic env validation, limits
│   │   ├── database.py           # Async engine, sessionmaker, Base model
│   │   ├── redis.py              # Redis client initialization & lifespan
│   │   └── security.py           # Password hashing, JWT token generation
│   ├── modules/
│   │   ├── auth/                 # User model, registration, login, JWT dependencies
│   │   ├── companies/            # Company, CompanyUser models & tenancy routes
│   │   ├── email_accounts/       # EmailAccount, EmailAccountAccess models & routes
│   │   ├── emails/               # Core email domain
│   │   │   ├── models.py         # Email, EmailThread, EmailTemplate, EmailSignature, EmailAttachment
│   │   │   ├── routes.py         # REST endpoints for emails, drafts, threads, attachments, signatures
│   │   │   ├── draft_service.py  # Draft CRUD, autosave, send, duplicate-safe signature preservation
│   │   │   ├── mailbox_service.py# Listing, pagination, search, folders, soft-delete
│   │   │   ├── thread_service.py # Thread reconciliation, message ordering, snippet updates
│   │   │   ├── sync_service.py   # IMAP sync coordination & message persistence
│   │   │   ├── attachment_service.py # File storage, upload, download, deletion
│   │   │   ├── template_service.py   # Email templates CRUD & application
│   │   │   ├── signature_service.py  # Email signatures CRUD, default toggling, content application
│   │   │   └── dashboard_service.py  # Analytics, counters, time-range trends
│   │   └── health/               # Health check endpoints
│   ├── services/
│   │   ├── smtp/                 # SMTP client, adapters, TLS/SSL connection handling
│   │   └── imap/                 # IMAP client, MIME parsing, bounce classification
│   ├── workers/
│   │   ├── celery_app.py         # Celery app & beat configuration
│   │   └── tasks.py              # Periodic & async background tasks (sync, cleanup)
│   └── main.py                   # FastAPI application factory, middleware, router mounts
├── pyproject.toml                # Poetry/pip build configuration & dependencies
└── tests/                        # Comprehensive pytest test suite (17+ test modules)
```

---

## 17. Frontend Codebase Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── accounts/             # Account cards, connect modal, access management
│   │   ├── compose/
│   │   │   ├── AttachmentUploadList.tsx # List of uploaded draft attachments
│   │   │   ├── RecipientInput.tsx       # Pill/chip email recipient input with validation
│   │   │   ├── RichTextEditor.tsx       # Contenteditable HTML editor with preserved cursor fix
│   │   │   ├── SignatureModal.tsx       # Signature selection modal
│   │   │   └── TemplateModal.tsx        # Template selection modal
│   │   ├── dashboard/            # ActivityTrendChart, StatCards, HealthWidget
│   │   ├── mailbox/
│   │   │   ├── EmailDetailDrawer.tsx    # Slide-over reading pane with draft edit button
│   │   │   ├── EmailRow.tsx             # Mailbox list item with selection & star
│   │   │   ├── MailboxHeader.tsx        # Folder title, unread badges, manual sync button
│   │   │   └── MailboxToolbar.tsx       # Gmail-style compact single-row responsive toolbar
│   │   ├── signatures/
│   │   │   ├── DeleteSignatureModal.tsx # Delete confirmation modal
│   │   │   ├── SignatureCard.tsx        # Signature preview card with badges & actions
│   │   │   ├── SignatureDrawer.tsx      # Slide-over create/edit drawer with live preview
│   │   │   └── SignaturePreviewModal.tsx# Full preview modal for signatures
│   │   └── ui/                   # Reusable buttons, cards, modals, empty states
│   ├── hooks/
│   │   └── useAuth.tsx           # Authentication state context
│   ├── layouts/
│   │   ├── AppLayout.tsx         # Main application layout with PulseMail sidebar
│   │   └── AuthLayout.tsx        # Login & registration layout
│   ├── pages/
│   │   ├── ComposePage.tsx       # Email composition with automatic draft saving & signature handling
│   │   ├── DashboardPage.tsx     # Extended analytics (Today to All Time)
│   │   ├── MailboxPage.tsx       # Folder views, pagination (25-200), search, bulk actions
│   │   ├── EmailDetailPage.tsx   # Full-page email viewer with Continue Editing Draft
│   │   ├── EmailAccountsPage.tsx # Email account management
│   │   ├── TemplatesPage.tsx     # Template management
│   │   ├── SignaturesPage.tsx    # Signature management with Stitch-inspired UI
│   │   ├── TeamPage.tsx          # Team & company membership management
│   │   └── DiagnosticsPage.tsx   # System logs & operational health
│   ├── services/
│   │   └── api.ts                # Authoritative typed Axios/fetch API client wrapper (includes signaturesApi)
│   └── types/
│       ├── emails.ts             # EmailItem, DraftPayload, AttachmentItem, Signature interfaces
│       └── dashboard.ts          # DateRangePreset, DashboardStats interfaces
```

---

## 18. Historical Milestones & Recent Commits

### 18.1 Foundations (M1 – M14)
- **M1:** Foundation, Docker Compose, FastAPI, PostgreSQL.
- **M2:** Authentication (bcrypt, JWT).
- **M3:** Multi-tenancy & Companies (roles: OWNER, ADMIN, MEMBER).
- **M4:** Email Accounts & Fernet-encrypted credentials.
- **M5:** SMTP Sending (STARTTLS/SSL, delivery status).
- **M6:** IMAP Sync (UID tracking, deduplication, Celery task).
- **M7:** Conversation Threading (In-Reply-To, References chain traversal).
- **M8:** Mailbox UI (Inbox, Sent, Drafts, Responses, Bounced, Trash).
- **M9:** Compose & Drafts.
- **M10:** Email Templates.
- **M11:** Email Signatures.
- **M12:** Email Attachments (25MB limit, disk storage).
- **M13:** Diagnostics & Monitoring.
- **M14:** Background Jobs (Celery Beat periodic sync).

### 18.2 Recent Production Milestones (September – October 2026)
- **Commit `3a6b991` (`feat: improve dashboard analytics and mailbox UX`):**
  - Added extended dashboard time ranges (`Today` to `All Time`) and adaptive granularity.
  - Gmail-style compact single-row responsive mailbox toolbar with conditional bulk actions.
  - Mailbox pagination bug fix (`keepPreviousData`).
- **Commit `f20832b` (`feat: implement automatic draft saving`):**
  - Removed manual "Save as Draft" button.
  - Implemented 900ms debounced autosave with in-flight request serialization and `latestStateRef`.
  - Added "Continue Editing Draft" in drawer and full-page email readers.
- **Commit `e9c444a` (`feat(templates): complete email template management`):**
  - Robust template management and active template filtering in Compose.
  - Fixed template cache invalidation (`["templates", accountId, "active"]`).
  - Implemented CSS inlining using `premailer` so template layouts survive email clients.
- **Commit `eb7ba61` (`docs: add workflow HTML diagrams, project context, and repository configuration`):**
  - Added interactive workflow HTML sequence diagrams and architecture specifications.
- **Commit `e6c31a8` (`fix: complete email signature integration`):**
  - Implemented Stitch-inspired Email Signatures module with drawer and live preview.
  - Fixed `comp_user.role` string type error in `SignatureService.list_signatures`.
  - Preserved default signature during draft autosave (`EmailDraftService.update_draft`).
  - Added duplicate signature protection and seamless account switching in Compose.
  - Expanded regression tests (34 tests in `test_email_signatures.py`).

---

## 19. Critical Historical Bug Fixes (Never Regress)

1. **Rich Text Editor Cursor Jumps:**
   - *Issue:* Typing in `RichTextEditor.tsx` previously caused cursor jumping or focus loss when parent state updated `initialHtml`.
   - *Fix:* Added `isInitialized` and `lastReportedHtmlRef`. The editor never resets DOM `innerHTML` if the external prop change was caused by the user's local keystrokes.
2. **Oversized Attachment Error Stickiness:**
   - *Issue:* Uploading a file > 25MB showed an error banner that persisted even after the user removed the invalid file.
   - *Fix:* Added `isAttachmentError` helper and explicitly cleared errors when files are removed or valid files are selected.
3. **Reply-to-Reply Thread Splitting:**
   - *Issue:* Replying to a customer reply previously created an isolated second thread instead of appending to the original conversation.
   - *Fix:* Thread resolution inspects the complete ancestor chain in `References` and preserves `replyThreadId` and `replyInReplyTo`.
4. **Dashboard Bounced Email Discrepancy:**
   - *Issue:* Mailbox Bounced folder showed emails while the Dashboard card showed 0 due to strict 7-day/30-day date boundaries.
   - *Fix:* Added `All Time` range support, aligning authorization scope and count query definitions.
5. **Mailbox Pagination Reset:**
   - *Issue:* Navigating mailbox pages sometimes clamped `currentPage` back to 1 before data finished loading.
   - *Fix:* Integrated `placeholderData: keepPreviousData` in React Query; clamped page only after data has loaded with total > 0.
6. **Template List Refresh on Mutation:**
   - *Issue:* Newly created or reactivated templates didn't appear in Compose without a hard reload.
   - *Fix:* Invalidated React Query key `["templates", selectedAccountId, "active"]` on create, activate, deactivate, and delete.
7. **HTML Template Styling Stripped by Email Clients:**
   - *Issue:* Received template emails lost styling (centered cards, colors, font styling) because email clients strip `<style>` tags.
   - *Fix:* Pre-processed outgoing HTML emails with `premailer` to convert embedded styles into inline HTML attributes.
8. **Signature Listing Role Type Error:**
   - *Issue:* `AttributeError: 'str' object has no attribute 'role'` when opening the Signatures page.
   - *Fix:* `CompanyService.get_user_companies()` returns `(Company, str_role)` tuples; pass role string directly without calling `.role`.
9. **Default Signature Disappearing During Draft Autosave:**
   - *Issue:* Default signature was attached on draft creation, but subsequent autosaves sent without `signature_id` wiped it out.
   - *Fix:* In `EmailDraftService.update_draft()`, when `signature_id is None`, resolve `SignatureService.get_default_signature()` and apply it using duplicate-safe logic. In Compose, preview signature separately from editor body state.

---

## 20. Testing & Verification Conventions

### 20.1 Backend Tests (Inside Docker)
- Execute tests inside the running Docker container:
  ```bash
  docker exec email_monitoring_backend pytest tests/<test_file>.py
  ```
- Key test files:
  - `tests/test_email_signatures.py` (34 tests covering default signatures, autosave lifecycle, permissions).
  - `tests/test_compose_drafts.py` (23 tests covering autosave, drafts, threading).
  - `tests/test_email_attachments.py` (Attachment limits, draft attachments).
  - `tests/test_email_templates.py` (Template CRUD, active filtering).
- **Targeted Testing:** Run only the relevant test file(s) for the current task. Do not run the entire suite unnecessarily.
- **Integrity Rule:** **NEVER** alter test assertions to artificially mask bugs. If a test fails, fix the application code.

### 20.2 Frontend Verification
- TypeScript compilation & bundling:
  ```bash
  cd frontend && npm run build
  ```
- Deploy built bundle to running Nginx container:
  ```bash
  docker cp frontend/dist/. email_monitoring_frontend:/usr/share/nginx/html/
  ```

---

## 21. Mandatory Development Rules for AI Agents

1. **Inspect Before Modifying:** Always inspect the actual working tree and source files before writing code.
2. **No Unrequested Browser Automation:** Do **NOT** use Playwright, Cypress, or browser subagents unless the user explicitly requests browser testing. The user finds that browser automation gets stuck.
3. **No Automatic Git Commits or Pushes:** Never run `git commit` or `git push` unless the user explicitly gives a commit command.
4. **Preserve Architectural Layering:**
   - Keep FastAPI routes thin; put business logic in service classes.
   - Keep React editor state separate from signature/template metadata to avoid cursor jumping and DOM pollution.
5. **Preserve Multi-Tenancy & Authorization Boundaries:** Never bypass company checks or email account permission checks.
6. **Protect Database Infrastructure:**
   - Never stop or touch the host machine's native PostgreSQL installation.
   - Never run `docker compose down -v`.
7. **No Mock / Fake Data:** Use real database models and standard API endpoints.

---

## 22. Protocol for Executing Tasks in New Chats

When starting any new task in a new chat:
1. **Read This Document:** Review `PROJECT_CONTEXT.md` to ground all decisions.
2. **Inspect Git Status & Source:** Run `git status` and inspect the target files.
3. **Plan Smallest Architectural Fix:** Adhere to existing patterns (services, React Query, Pydantic schemas).
4. **Execute Code Edits:** Use surgical file replacements.
5. **Verify Backend & Frontend:**
   - Run relevant pytest tests via `docker exec email_monitoring_backend pytest ...`.
   - Run `npm run build` in `frontend/`.
6. **Report Clearly:** Detail exact root cause, files changed, verification results, and remaining manual browser test steps.
7. **Wait for User:** Stop without committing.

---

## 23. Authoritative File Index

| Path | Responsibility |
| :--- | :--- |
| `docker-compose.yml` | Container definitions, ports, volumes, health checks. |
| `backend/app/main.py` | FastAPI application initialization and router mounts. |
| `backend/app/core/config.py` | Environment settings, database URLs, 25MB upload limit. |
| `backend/app/core/database.py` | Async engine, sessionmaker, and Base model. |
| `backend/app/modules/emails/models.py` | `Email`, `EmailThread`, `EmailTemplate`, `EmailSignature`, `EmailAttachment`. |
| `backend/app/modules/emails/routes.py` | Email, draft, template, signature HTTP REST endpoints. |
| `backend/app/modules/emails/draft_service.py` | Authoritative draft CRUD, autosave, sending, and duplicate-safe signature preservation. |
| `backend/app/modules/emails/mailbox_service.py` | Folder listing, pagination, sorting, search, and soft-delete. |
| `backend/app/modules/emails/thread_service.py` | In-Reply-To and References conversation thread resolution. |
| `backend/app/modules/emails/sync_service.py` | IMAP synchronization and incoming email persistence. |
| `backend/app/modules/emails/attachment_service.py` | Upload, download, validation, and disk storage of attachments. |
| `backend/app/modules/emails/template_service.py` | Email templates CRUD, active filtering, CSS inlining with `premailer`. |
| `backend/app/modules/emails/signature_service.py` | Email signatures CRUD, default signature toggling, duplicate-safe insertion. |
| `backend/app/modules/emails/dashboard_service.py` | Analytics counters and time-range trend queries. |
| `backend/app/workers/celery_app.py` | Celery application and periodic beat schedule definition. |
| `backend/app/workers/tasks.py` | Celery background task implementations. |
| `frontend/src/pages/ComposePage.tsx` | Message compose interface with debounced automatic draft saving & signature preview. |
| `frontend/src/pages/MailboxPage.tsx` | Mailbox folder tables, pagination, and bulk actions. |
| `frontend/src/pages/SignaturesPage.tsx` | Stitch-inspired signature management page (filtering, preview, create/edit drawer). |
| `frontend/src/pages/TemplatesPage.tsx` | Template management page. |
| `frontend/src/pages/EmailDetailPage.tsx` | Full-page email reading view with draft reopening support. |
| `frontend/src/components/mailbox/EmailDetailDrawer.tsx` | Drawer email reader with "Continue Editing Draft" action. |
| `frontend/src/components/mailbox/MailboxToolbar.tsx` | Compact single-row responsive mailbox toolbar. |
| `frontend/src/components/compose/RichTextEditor.tsx` | Safe contenteditable editor with cursor stability fix. |
| `frontend/src/components/signatures/SignatureDrawer.tsx` | Slide-over drawer for creating/editing signatures with live preview. |
| `frontend/src/services/api.ts` | Frontend API client communicating with backend endpoints (`emailsApi`, `signaturesApi`, `templatesApi`). |
| `frontend/src/types/emails.ts` | TypeScript interfaces for emails, drafts, templates, attachments, and signatures. |
