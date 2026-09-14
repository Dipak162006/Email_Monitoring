# Email Monitoring System
## Master Product Requirements and Architecture Specification

**Status:** Master Specification  
**Project Type:** Standalone application  
**Purpose:** Email monitoring and management platform  
**Reference Product:** Brevo-style product/UX inspiration only  
**ERP Dependency:** None  
**Future Goal:** Clean architecture suitable for future ERP/enterprise integration

---

# 1. Project Objective

Build a standalone, production-quality Email Monitoring System that allows company users to manage company email accounts, send and receive emails, monitor email activity, create reusable templates and signatures, manage attachments, and view email statistics.

The application is inspired by products such as Brevo for product ideas and user experience only.

Brevo is NOT a provider, dependency, API integration, or infrastructure component of this project.

The system must be provider-independent and support company email accounts through SMTP and IMAP where applicable.

---

# 2. Core Product Model

Application login and email accounts are separate concepts.

A user logs into the application using their own application account.

The user can then access one or more company email accounts for which they have permission.

Example:

Company:
- SevenCore

Users:
- Alice
- Bob

Email accounts:
- sales@company.com
- support@company.com

Access:
- Alice -> sales@company.com, support@company.com
- Bob -> support@company.com

A user's login email must NOT automatically become the sending/receiving email account.

When composing an email, the user selects an authorized email account in the From field.

---

# 3. Main Functional Areas

The system contains:

1. Authentication
2. Users and companies
3. Company email account management
4. SMTP email sending
5. IMAP mailbox synchronization
6. Mailbox management
7. Email threading
8. Bounce monitoring
9. Response/reply monitoring
10. Email templates
11. Signatures
12. Attachments
13. Dashboard and statistics
14. Search and filtering
15. Background processing
16. Authorization
17. Error handling
18. Testing
19. Deployment and documentation

---

# 4. Technology Stack

## Backend

- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- PostgreSQL
- Alembic
- JWT-based authentication
- Secure password hashing
- Redis
- Celery

## Email

- SMTP for sending
- IMAP for receiving and mailbox synchronization
- Python email parsing facilities where appropriate

## Frontend

- React
- TypeScript
- Vite
- Tailwind CSS
- shadcn/ui
- TanStack Query
- React Router
- TipTap or another suitable rich-text editor

## Infrastructure

- Docker
- Docker Compose
- Nginx
- PostgreSQL
- Redis
- Celery worker

## Testing

- pytest
- HTTPX for API testing
- Vitest
- React Testing Library

---

# 5. High-Level Architecture

The application must use a layered, modular architecture.

```text
React Frontend
      |
      v
FastAPI REST API
      |
      v
Route Layer
      |
      v
Service Layer
      |
      v
Repository / Data Access Layer
      |
      v
SQLAlchemy
      |
      v
PostgreSQL
```

Email infrastructure:

```text
Email Service
      |
      +----------------+
      |                |
      v                v
SMTP Service       IMAP Service
      |                |
      v                v
Email Provider     Email Provider
```

Background processing:

```text
Celery
  |
Redis
  |
  +---- Mailbox synchronization
  +---- Incoming email processing
  +---- Bounce processing
  +---- Reply detection
  +---- Queued email processing
```

Frontend communication:

```text
React
  |
TanStack Query
  |
REST API
  |
FastAPI
```

---

# 6. Architecture Rules

These rules apply throughout the entire project.

## Rule 1: Standalone Project

Do not depend on the ERP repository, ERP framework, ERP database, or ERP-specific APIs.

The project must run independently.

## Rule 2: Future Integration

Although standalone, the architecture must use clean boundaries so the system can later be integrated into an ERP or another enterprise platform.

Business logic must not depend on the frontend.

Business logic must not depend directly on ERP code.

Provider-specific logic must be isolated.

## Rule 3: Separation of Responsibilities

Do not put business logic directly inside FastAPI route handlers.

Use:

```text
Route
  -> Service
  -> Repository
  -> Database
```

Email infrastructure should be isolated behind services/adapters.

## Rule 4: No Provider Hardcoding

Do not scatter Google/Yahoo/Zoho-specific conditions throughout the code.

Use a provider abstraction or adapter architecture.

## Rule 5: Backend Is the Security Source of Truth

Frontend permission checks are only for user experience.

All access restrictions must be enforced by the backend.

## Rule 6: No Secrets in Source Code

Never hardcode:
- passwords
- API keys
- tokens
- private keys
- SMTP credentials
- IMAP credentials

Use environment configuration and secure credential storage.

## Rule 7: No Credential Exposure

Email credentials must never be returned through normal API responses or exposed to the frontend.

Stored email credentials must be protected/encrypted.

## Rule 8: Validate Everything

Validate:
- API input
- email addresses
- uploaded files
- attachment sizes
- template variables
- provider configuration

## Rule 9: Do Not Trust Email HTML

HTML email content must be handled safely and sanitized where it is rendered in the application.

## Rule 10: Server-Side Filtering

Mailbox search, filtering, sorting and pagination should be performed server-side.

Do not download the entire mailbox into the browser and filter it in React.

## Rule 11: Database Integrity

Use proper:
- foreign keys
- indexes
- unique constraints
- nullability
- relationships
- transactions

Do not duplicate data unnecessarily.

## Rule 12: Test Before Expanding

Implement a feature, test it, verify it, then move to the next dependent feature.

Do not generate the entire application blindly.

---

# 7. Authentication

The application must support:

- User registration where required
- Login
- Logout/session handling
- Password hashing
- JWT or equivalent secure authentication
- Protected API endpoints

Application login identity is separate from email account identity.

Example:

```text
User
  login_email = alice@company.com

EmailAccount
  email_address = sales@company.com
```

---

# 8. Companies and Users

The system must support company-level ownership.

Core concepts:

```text
Company
User
CompanyUser
EmailAccount
EmailAccountAccess
```

Users may have access to multiple email accounts.

An email account may be accessible by multiple users.

Example:

```text
Sales Account
  |
  +-- Alice
  +-- Bob
```

Users must only access email accounts assigned to them.

---

# 9. Email Account Configuration

The application must allow users with appropriate permissions to configure email accounts.

Supported provider categories:

- Google
- Yahoo
- Zoho
- Custom SMTP/IMAP

Provider support must be designed so additional providers can be added later.

Configuration should support:

- Account name
- Email address
- Provider
- SMTP host
- SMTP port
- SMTP security
- IMAP host
- IMAP port
- IMAP security
- Authentication information
- Active/inactive state
- Connection status

The UI must provide:

- Test SMTP connection
- Test IMAP connection
- Save
- Edit
- Disable/enable
- Remove/disconnect

Not every provider must necessarily support both SMTP and IMAP. The system must model sending and receiving capabilities separately.

---

# 10. SMTP Sending

SMTP is responsible for sending outgoing emails.

Flow:

```text
Compose Email
    |
    v
FastAPI
    |
    v
Email Service
    |
    v
Selected Email Account
    |
    v
SMTP Adapter
    |
    v
Provider SMTP Server
    |
    v
Recipient
```

The selected From account must be one the current user is authorized to use.

The system should persist the email and its state.

Potential states include:

- DRAFT
- QUEUED
- SENDING
- SENT
- FAILED
- BOUNCED

The exact state machine must be finalized during implementation.

---

# 11. IMAP Receiving

IMAP is responsible for receiving/synchronizing mailbox messages.

Flow:

```text
IMAP Server
    |
    v
Background Worker
    |
    v
Email Parser
    |
    v
Email Service
    |
    v
Database
    |
    v
Mailbox UI
```

Incoming email processing should capture, where available:

- Message-ID
- In-Reply-To
- References
- Sender
- Recipients
- CC
- BCC
- Subject
- Text body
- HTML body
- Received date
- Attachments

The system must avoid creating duplicate email records during repeated synchronization.

---

# 12. Email Model

The email domain should represent at least:

- Account
- Thread
- Message ID
- Direction
- Status
- Sender
- Recipients
- CC
- BCC
- Subject
- Text body
- HTML body
- Read/unread state
- Star/mark state
- Sent/received timestamps
- Creation/update timestamps

Direction should be separate from status.

Example:

```text
direction = OUTGOING
status = SENT
```

or:

```text
direction = INCOMING
status = RECEIVED
```

---

# 13. Email Threads and Responses

Responses must be associated with the original conversation where possible.

Use standard email headers such as:

- Message-ID
- In-Reply-To
- References

Example:

```text
Thread
 |
 +-- Original email
 +-- Customer reply
 +-- Our reply
 +-- Customer reply
```

The system must distinguish between an arbitrary incoming email and a response to an outgoing email.

The exact response-count definition must be explicitly decided before dashboard implementation.

---

# 14. Bounce Monitoring

Bounce handling must not assume that successful SMTP submission means final delivery.

Conceptual flow:

```text
Send
  |
  v
SMTP accepted
  |
  v
SENT
  |
  v
Bounce notification
  |
  v
Background processing
  |
  v
Match original email
  |
  v
BOUNCED
```

Bounce processing must be isolated from the dashboard.

The dashboard reads already-processed status data.

---

# 15. Mailbox

The mailbox must provide:

- Inbox
- Sent
- Drafts
- Bounced
- Responses
- Trash

Core operations:

- Open email
- Send email
- Receive/synchronize email
- Mark read/unread
- Star/mark
- Delete
- Download attachments
- Search
- Filter
- Sort
- Pagination

The exact meaning of "mark" should be implemented as clear mailbox actions such as read/unread and starred unless business requirements specify otherwise.

---

# 16. Compose Email

The compose interface must support:

- From account selection
- To
- CC
- BCC
- Subject
- Rich text body
- HTML email
- Template selection
- Signature selection
- Attachments
- Save draft
- Send

The From dropdown must only display authorized email accounts.

---

# 17. Email Templates

Templates must support CRUD operations:

- Create
- Read
- Update
- Delete

Template data:

- Template name
- Subject
- Text body
- HTML body
- Variables
- Attachments
- Signature

Example:

```text
Subject:
Welcome {{customer_name}}

Body:
Hello {{customer_name}},
Welcome to our platform.
```

Template rendering must be safe.

Do not allow template variables to execute arbitrary application code.

---

# 18. Signatures

The system must support reusable signatures.

Operations:

- Create
- Read
- Update
- Delete
- Set default

A signature should support text and/or HTML content.

Signatures must be usable:

- Directly in compose
- Inside templates

---

# 19. Attachments

Support attachments for:

1. Individual emails
2. Templates

Required operations:

- Upload
- Associate
- Download
- Remove

Security requirements:

- File size limits
- Safe filenames
- File type validation
- Secure storage
- Do not expose internal storage paths unnecessarily

Start with local storage if appropriate, but keep a storage abstraction so S3-compatible storage can be added later.

---

# 20. Dashboard

The dashboard must provide at minimum:

```text
Sent
Bounced
Responses
```

Example:

```text
+----------------+----------------+----------------+
| SENT           | BOUNCED        | RESPONSES      |
|                |                |                |
| 12,450         | 342            | 1,245          |
+----------------+----------------+----------------+
```

The statistics must come from real database data.

Do not use hardcoded/demo numbers in the final implementation.

Optional later dashboard features:

- Recent email activity
- Activity over time
- Account-level statistics
- Delivery statistics

---

# 21. Dashboard Navigation

Dashboard cards must be interactive.

Example:

```text
Dashboard
   |
   +-- Sent
   |      |
   |      v
   |   Mailbox?status=sent
   |
   +-- Bounced
   |      |
   |      v
   |   Mailbox?status=bounced
   |
   +-- Responses
          |
          v
       Mailbox?status=replied
```

The mailbox filter must be applied through the backend API.

---

# 22. Search and Filtering

Mailbox search/filtering should support, where appropriate:

- Status
- Email account
- Sender
- Recipient
- Subject
- Date range
- Read/unread
- Starred
- Text search

Pagination must be server-side.

Example:

```text
GET /api/v1/emails?status=bounced&page=1
```

---

# 23. Background Processing

Use background workers for tasks that should not block normal HTTP requests.

Potential jobs:

```text
sync_mailbox
process_incoming_email
detect_reply
process_bounce
send_queued_email
```

Workers must be safe to retry.

Mailbox synchronization must be idempotent so the same message is not repeatedly inserted.

---

# 24. API Architecture

Use versioned REST APIs.

Suggested base:

```text
/api/v1
```

Main resource groups:

```text
/api/v1/auth
/api/v1/users
/api/v1/companies
/api/v1/email-accounts
/api/v1/emails
/api/v1/templates
/api/v1/signatures
/api/v1/attachments
/api/v1/dashboard
```

Routes should remain thin.

Business logic belongs in services.

Database queries belong in repositories/data-access components where appropriate.

---

# 25. Suggested Backend Structure

```text
backend/
└── app/
    ├── main.py
    │
    ├── core/
    │   ├── config.py
    │   ├── database.py
    │   └── security.py
    │
    ├── modules/
    │   ├── auth/
    │   ├── users/
    │   ├── companies/
    │   ├── email_accounts/
    │   ├── emails/
    │   ├── templates/
    │   ├── signatures/
    │   └── dashboard/
    │
    ├── services/
    │   ├── email/
    │   ├── smtp/
    │   ├── imap/
    │   ├── template/
    │   └── storage/
    │
    ├── workers/
    │   ├── celery_app.py
    │   ├── email_sync.py
    │   └── email_processing.py
    │
    └── common/
```

Module structure may use:

```text
models.py
schemas.py
routes.py
service.py
repository.py
```

where appropriate.

Do not create files merely because they appear in this example if the implementation does not need them.

---

# 26. Suggested Frontend Structure

```text
frontend/
└── src/
    ├── app/
    ├── components/
    │   ├── ui/
    │   ├── layout/
    │   ├── email/
    │   └── dashboard/
    │
    ├── pages/
    │   ├── Login.tsx
    │   ├── Dashboard.tsx
    │   ├── Mailbox.tsx
    │   ├── EmailDetail.tsx
    │   ├── Compose.tsx
    │   ├── EmailAccounts.tsx
    │   ├── Templates.tsx
    │   └── Signatures.tsx
    │
    ├── services/
    │   └── api.ts
    │
    ├── hooks/
    ├── types/
    └── routes/
```

---

# 27. UI/UX Requirements

The UI is a major requirement.

It must look like a modern professional SaaS email product, not a generic CRUD admin panel.

Priorities:

- Clean dashboard
- Clear statistics cards
- Professional mailbox
- Easy compose experience
- Clear navigation
- Good typography
- Consistent spacing
- Clear status badges
- Responsive layout
- Good empty states
- Good loading states
- Good error states
- Confirmation dialogs for destructive operations
- Toast/notification feedback
- Accessible controls

The UI should take inspiration from professional email products without copying another product's branding or proprietary design.

---

# 28. Security Requirements

Security is critical because the system handles email credentials and potentially sensitive email content.

Required:

- Secure password hashing
- Authentication
- Backend authorization
- Encrypted email credentials
- HTTPS in production
- Input validation
- HTML sanitization
- Attachment validation
- Attachment size limits
- Secure file storage
- No secrets in source code
- No secrets in frontend
- No credentials in logs
- No sensitive credentials in API responses
- User/company data isolation

A user must never be able to access another user's or unauthorized company's email account through API manipulation.

---

# 29. Database Design Principles

The database must be normalized and relational.

Core entities are expected to include:

```text
Company
User
CompanyUser
EmailAccount
EmailAccountAccess
Email
EmailThread
EmailAttachment
EmailTemplate
TemplateAttachment
Signature
```

The exact fields and relationships must be finalized before implementation.

Consider:

- Foreign keys
- Unique constraints
- Indexes
- Nullability
- Cascading behavior
- Ownership
- Tenant/company isolation
- Timestamps

Do not add unnecessary tables or duplicate data.

---

# 30. Error Handling

The system must provide meaningful errors.

Backend should distinguish:

- Authentication errors
- Authorization errors
- Validation errors
- Provider connection errors
- SMTP errors
- IMAP errors
- Database errors
- File errors
- Template errors

Do not expose internal stack traces or credentials to users.

Log useful technical information without logging secrets.

---

# 31. Testing Strategy

Tests must be added throughout development.

Backend tests should cover:

- Authentication
- Authorization
- Company/user access
- Email account CRUD
- SMTP behavior
- IMAP parsing
- Duplicate synchronization prevention
- Email creation
- Template rendering
- Signature insertion
- Attachment validation
- Bounce processing
- Reply detection
- Dashboard statistics
- Mailbox filters

API tests should verify successful and failure cases.

Frontend tests should cover important user flows such as:

```text
Login
Open dashboard
Click Sent
See filtered mailbox
Compose email
Select email account
Send email
Create template
Create signature
```

---

# 32. Development Milestones

The application must be implemented incrementally.

## M1 — Foundation

- Repository/project setup
- Backend setup
- Frontend setup
- PostgreSQL
- SQLAlchemy
- Alembic
- Docker
- Environment configuration
- Health check

## M2 — Authentication

- User model
- Registration if required
- Login
- Password hashing
- JWT
- Protected APIs

## M3 — Companies and Access

- Company model
- User/company relationship
- Email account access model
- Backend authorization

## M4 — Email Account Configuration

- Account CRUD
- SMTP configuration
- IMAP configuration
- Provider abstraction
- Connection testing
- Credential protection

## M5 — SMTP Engine

- SMTP service
- Send email
- Email persistence
- Status handling
- Error handling

## M6 — IMAP Engine

- IMAP connection
- Mail synchronization
- Email parsing
- Duplicate prevention
- Persistence

## M7 — Email Threads

- Message identifiers
- Reply matching
- Thread creation
- Thread retrieval

## M8 — Mailbox

- Inbox
- Sent
- Drafts
- Bounced
- Responses
- Trash
- Read/unread
- Star
- Delete
- Email detail

## M9 — Compose

- To/CC/BCC
- Subject
- Rich text
- HTML
- Draft
- Send

## M10 — Templates

- Template CRUD
- Variables
- Text/HTML
- Preview
- Template selection

## M11 — Signatures

- Signature CRUD
- Default signature
- Compose integration
- Template integration

## M12 — Attachments

- Upload
- Storage
- Email attachments
- Template attachments
- Download
- Validation

## M13 — Monitoring

- Bounce processing
- Reply detection
- Status updates
- Monitoring workers

## M14 — Background Jobs

- Celery
- Redis
- Mail sync scheduling
- Email processing
- Retry handling

## M15 — Dashboard

- Sent count
- Bounce count
- Response count
- Recent activity if required

## M16 — Dashboard Navigation

- Sent card -> filtered mailbox
- Bounce card -> filtered mailbox
- Response card -> filtered mailbox

## M17 — Search and Filters

- Search
- Filters
- Sorting
- Pagination

## M18 — UI/UX Polish

- Responsive design
- Loading
- Empty states
- Error states
- Notifications
- Accessibility

## M19 — Testing

- Unit tests
- Integration tests
- API tests
- Frontend tests
- End-to-end critical flows

## M20 — Security Review

- Authorization review
- Credential review
- File upload review
- HTML review
- API security review
- Secret review

## M21 — Deployment

- Docker production configuration
- Nginx
- PostgreSQL
- Redis
- Celery
- Environment configuration
- Health checks

## M22 — Documentation

- README
- Architecture documentation
- API documentation
- Database documentation
- Deployment instructions
- Configuration instructions

## M23 — Final Review

Verify:

- All requirements
- All major user flows
- Authorization
- Error handling
- Database integrity
- UI quality
- Provider behavior
- Background jobs
- Tests
- Deployment

---

# 33. Implementation Rules for AI Coding Agents

Antigravity or any other coding agent must follow these rules.

1. Do not generate the entire application blindly in one step.
2. Work milestone by milestone.
3. Before changing existing code, inspect the relevant files.
4. Do not invent existing functionality.
5. Do not create duplicate services or abstractions unnecessarily.
6. Reuse existing project code when appropriate.
7. Keep routes thin.
8. Keep business logic in services.
9. Keep database access organized.
10. Keep provider-specific logic isolated.
11. Never hardcode secrets.
12. Never expose credentials.
13. Do not weaken authorization to make functionality work.
14. Add tests for important behavior.
15. Run focused tests after each significant change.
16. Do not modify tests simply to hide broken behavior.
17. Do not introduce unnecessary dependencies.
18. Prefer simple maintainable implementations.
19. Document important architectural decisions.
20. If a requirement is ambiguous, identify the ambiguity instead of silently inventing behavior.
21. If implementation choices have significant architectural consequences, explain them before proceeding.
22. Preserve backward compatibility when changing already-used APIs.
23. Keep the application independently runnable.
24. Keep future ERP integration possible through clean API/service boundaries.
25. Never treat Brevo as a provider or dependency.

---

# 34. Important Product Decisions

The following decisions are fixed:

- This is a standalone project.
- Brevo is inspiration only.
- Brevo is not integrated.
- SMTP is used for sending.
- IMAP is used for receiving where supported.
- Application login is separate from email accounts.
- Users can access company email accounts based on authorization.
- Multiple users may access the same company email account.
- A user may access multiple email accounts.
- The From account must be selected from authorized accounts.
- Backend authorization is mandatory.
- Dashboard statistics must use real persisted data.
- Dashboard cards must navigate to filtered mailbox views.
- The architecture must be provider-independent.
- The architecture must remain suitable for future ERP integration.

---

# 35. Decisions That Must Be Confirmed During Implementation

Do not silently assume answers for these questions:

1. Exact definition of response count
2. Exact bounce detection strategy for each provider
3. Whether OAuth is required for Google/Yahoo/Zoho
4. Exact provider authentication mechanisms
5. Trash/permanent deletion behavior
6. Exact meaning of "mark email"
7. Maximum attachment size
8. Allowed attachment types
9. Local vs object storage for production
10. Whether scheduled email sending is required
11. Whether real-time mailbox updates are required
12. Company administrator/role requirements
13. Exact dashboard analytics beyond the three required cards

If a decision is required, document it before implementing dependent functionality.

---

# 36. Definition of Done

The project is considered complete only when:

- Users can securely log in.
- Companies and users are isolated correctly.
- Authorized users can configure email accounts.
- SMTP sending works.
- IMAP receiving/synchronization works where supported.
- Emails are persisted correctly.
- Duplicate synchronization is prevented.
- Replies can be associated with conversations where possible.
- Bounce processing works according to the supported provider strategy.
- Mailbox functionality works.
- Templates work.
- Signatures work.
- Attachments work securely.
- Dashboard statistics are accurate.
- Dashboard cards navigate to correctly filtered mailbox results.
- Search/filter/pagination work.
- Unauthorized users cannot access protected email accounts.
- Important backend behavior is tested.
- Application can run using documented setup instructions.
- Production configuration is documented.
- No secrets are committed.
- UI is professional and usable.
- The system remains independent from ERP infrastructure.

---

# 37. Guiding Principle

The goal is not merely to make a demo that appears to work.

The goal is to build a clean, modular, secure and maintainable standalone email platform that can later be integrated into an enterprise/ERP environment without rewriting the core email functionality.

When choosing between a quick implementation and a clean architecture, prefer the clean architecture as long as it does not introduce unnecessary complexity.

Antigravity must treat this document as the master specification. If a requirement is unclear or conflicts with an implementation detail, stop and identify the issue rather than silently inventing behavior.
