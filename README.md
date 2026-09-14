# Email Monitoring System

A standalone, production-quality email monitoring and management platform built with FastAPI, SQLAlchemy 2.x, PostgreSQL, Redis, Celery, and React + Vite + TypeScript.

Inspired by modern SaaS platforms (such as Brevo) for UX/product workflows only. **This is a 100% standalone system with zero ERP dependencies and zero third-party platform lock-in.**

---

## Architecture Overview

```text
React Frontend (Vite + TS + Tailwind)
         |
         v
FastAPI REST API (v1)
         |
         +---> Route Layer (Thin handlers)
         |
         +---> Service Layer (Business logic & domain rules)
         |
         +---> Repository Layer (Data access & queries)
         |
         +---> Database (PostgreSQL via SQLAlchemy 2.x asyncpg)
         |
         +---> Cache & Task Broker (Redis)
         |
         +---> Background Pipeline (Celery Workers for sync, bounces, replies)
```

---

## Directory Structure

```text
Email_Monitoring/
├── docker-compose.yml          # Container orchestration (Postgres, Redis, API, Worker, Web)
├── .env.example                # Canonical environment template
├── .env                        # Local development environment (git-ignored)
├── .gitignore                  # Git ignore rules for Python, Node, secrets, etc.
├── README.md                   # Project documentation
│
├── backend/
│   ├── Dockerfile              # Production Python 3.12+ container
│   ├── requirements.txt        # Backend dependencies
│   ├── pyproject.toml          # Packaging and pytest configuration
│   ├── alembic.ini             # Alembic database migration configuration
│   ├── alembic/                # Migration scripts and environment
│   ├── app/
│   │   ├── main.py             # FastAPI entry point, CORS, and lifecycle
│   │   ├── core/               # Settings, database engine, redis, security
│   │   ├── modules/            # Business domains (health, auth, email, etc.)
│   │   ├── services/           # Reusable service layer
│   │   ├── workers/            # Celery worker application
│   │   └── common/             # Cross-cutting utilities
│   └── tests/                  # Pytest test suite (health, API probes)
│
└── frontend/
    ├── Dockerfile              # Multi-stage build with Nginx SPA server
    ├── nginx.conf              # SPA routing and /api reverse proxy
    ├── package.json            # Dependencies and scripts
    ├── tsconfig.json           # TypeScript configuration with @/* aliases
    ├── vite.config.ts          # Vite build and development proxy
    ├── tailwind.config.js      # Tailwind CSS tokens
    ├── index.html              # HTML shell with Google fonts
    └── src/
        ├── main.tsx            # React Query & app root mount
        ├── App.tsx             # M1 interactive diagnostics dashboard
        ├── index.css           # Design tokens, typography, and dark mode
        ├── services/api.ts     # Typed API client
        ├── components/         # UI and domain components
        └── pages/              # Routed pages
```

---

## Prerequisites

- **Python**: 3.12 or later
- **Node.js**: 20 or later (npm 10+)
- **Docker & Docker Compose**: Recommended for containerized deployment

---

## Quick Start Guide

### 1. Environment Setup

```bash
cp .env.example .env
```

### 2. Running Locally

#### Backend:
```bash
# Create and activate virtual environment
python -m venv .venv
# On Windows:
.\.venv\Scripts\activate
# On Linux/macOS:
# source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Run FastAPI server
uvicorn app.main:app --app-dir backend --reload --port 8000
```
- API Root: `http://localhost:8000`
- Interactive OpenAPI Docs: `http://localhost:8000/docs`
- Health Endpoint: `http://localhost:8000/api/v1/health`

#### Frontend:
```bash
cd frontend
npm install
npm run dev
```
- Frontend Dev Server: `http://localhost:5173`

---

### 3. Running with Docker Compose

To start PostgreSQL, Redis, FastAPI Backend, Celery Worker, and Frontend together:

```bash
docker compose up --build
```

---

## Running Checks & Tests

### Backend Tests
```bash
# Run pytest from project root
pytest backend/tests
```

### Frontend Build & Typecheck
```bash
cd frontend
npm run build
```

---

## Milestone Progress

- [x] **M1: Project Foundation** — Clean architecture setup, FastAPI, React + TS, DB & Redis integration hooks, Docker Compose, health endpoints.
- [ ] **M2: Authentication** — User models, JWT tokens, password hashing, protected endpoints.
- [ ] **M3: Companies and Access** — Multi-tenant company isolation, user permission mapping.
- [ ] **M4: Email Account Configuration** — SMTP/IMAP account settings, credential encryption.
- [ ] **M5-M6: SMTP & IMAP Engines** — Outgoing email sending & incoming mailbox sync.
- [ ] **M7-M23**: Threading, Mailbox UI, Compose, Templates, Signatures, Attachments, Monitoring, Polish.
