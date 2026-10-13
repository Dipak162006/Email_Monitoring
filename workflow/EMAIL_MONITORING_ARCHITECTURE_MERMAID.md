# Email Monitoring System — Mermaid Architecture Document

**Source:** `PROJECT_ARCHITECTURE_FLOWS.md`  
**Scope:** The architecture, authentication sequence, TypeScript-to-database lifecycle, and global error handling described in the source document.

> Validation note: Mermaid fences, diagram-family declarations, and structural references were checked statically. This is not proof of acceptance by every Mermaid renderer; no local Mermaid CLI renderer was available during preparation.

## Diagram index

1. **System architecture overview** — major frontend, backend, storage, and integration responsibilities.
2. **Authentication sequence** — login validation, credential verification, JWT issuance, `/auth/me`, and failure branches.
3. **Data model lifecycle** — typed frontend contracts through FastAPI/Pydantic/services/SQLAlchemy/PostgreSQL and back.
4. **Global error handling** — frontend HTTP handling and backend validation/service/database exception paths.

## 1. System architecture overview

```mermaid
flowchart LR
    User[End User]

    subgraph FE["Frontend · React 18 + TypeScript + Vite"]
        Pages[Pages and UI]
        Contexts[AuthContext · WorkspaceContext · NotificationContext]
        Client[apiClient · Fetch · JWT injection]
        Query[React Query · cache and refetch]
        Types[TypeScript interfaces]
        Pages --> Contexts
        Contexts --> Client
        Pages --> Query
        Query --> Client
        Types -. typed contracts .-> Client
    end

    subgraph BE["Backend · FastAPI"]
        Routes[Module routers]
        Schemas[Pydantic schemas]
        Services[Service layer]
        Models[SQLAlchemy ORM models]
        Routes --> Schemas
        Schemas --> Services
        Services --> Models
    end

    subgraph DATA["Persistence and background work"]
        PG[(PostgreSQL)]
        Redis[(Redis cache and broker)]
        Celery[Celery background workers]
        Alembic[Alembic migrations]
        Models --> PG
        Alembic -. schema migrations .-> PG
        Redis <--> Celery
        Celery --> PG
    end

    subgraph EXT["External email providers"]
        SMTP[SMTP adapter]
        IMAP[IMAP adapter]
    end

    User --> Pages
    Client <-->|HTTP / JSON · /api/v1| Routes
    Services --> SMTP
    Services --> IMAP
    Services <--> Redis
```

## 2. Global user session authentication

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Login as LoginPage
    participant Auth as AuthContext
    participant API as apiClient / authApi
    participant Router as Auth Router
    participant Schema as UserLogin Schema
    participant Service as Auth Service
    participant DB as Database Session
    participant Security as Security Utilities

    User->>Login: Submit email and password
    Login->>Auth: login(credentials)
    Auth->>API: authApi.login(credentials)
    API->>Router: POST /api/v1/auth/login
    Router->>Schema: Validate credentials

    alt Invalid request schema
        Schema-->>Router: Validation errors
        Router-->>API: 422 response
        API-->>Auth: RequestError(422)
        Auth-->>Login: Validation failure
        Login-->>User: Show field errors
    else Valid request schema
        Schema-->>Router: Validated credentials
        Router->>Service: authenticate_user(email, password)
        Service->>DB: Query user by email
        DB-->>Service: User record or none
        alt User missing or password invalid
            Service-->>Router: Authentication failure
            Router-->>API: 401 Unauthorized
            API->>API: Clear stored token
            API-->>Auth: RequestError(401)
            Auth-->>Login: Login failed
            Login-->>User: Show error
        else Credentials valid
            Service->>Security: verify_password()
            Security-->>Service: Valid
            Service->>Security: create_access_token(user_id)
            Security-->>Service: JWT access token
            Service-->>Router: Token response
            Router-->>API: 200 + JSON token
            API->>API: Store access token
            API-->>Auth: Token response
            Auth->>Auth: setToken(token)
            Auth->>API: GET /api/v1/auth/me
            API->>Router: GET /api/v1/auth/me + Bearer token
            Router->>DB: Resolve current user
            DB-->>Router: UserRead
            Router-->>API: 200 + UserRead
            API-->>Auth: User object
            Auth->>Auth: Set user and authenticated state
            Auth-->>Login: Login success
            Login-->>User: Navigate to /dashboard
        end
    end
```

## 3. TypeScript-to-database data lifecycle

```mermaid
flowchart TD
    subgraph FRONT["Frontend"]
        TS[TypeScript interface]
        API[Typed API client]
        Encode[Serialize request as JSON]
        Decode[Deserialize response]
        TS --> API --> Encode
        Decode --> TS
    end

    subgraph HTTP["HTTP / REST"]
        Req[JSON request]
        Res[JSON response]
        Encode --> Req
        Res --> Decode
    end

    subgraph BACK["FastAPI backend"]
        Router[Router handler]
        InSchema[Pydantic request schema]
        Service[Service layer]
        OutSchema[Pydantic response schema]
        Req --> Router --> InSchema --> Service --> OutSchema --> Res
    end

    subgraph DBL["Database layer"]
        Session[SQLAlchemy session]
        Model[SQLAlchemy model]
        Table[(PostgreSQL table)]
        Service --> Session
        Session --> Model
        Model --> Table
        Table --> Model
        Model --> Session
        Session --> Service
    end
```

## 4. Global API error handling

```mermaid
flowchart TD
    Request[Frontend API request] --> Client[apiClient]
    Client --> Backend[FastAPI router]
    Backend --> Validation{Pydantic validation}

    Validation -->|Invalid payload| E422[422 validation response]
    Validation -->|Valid payload| Service[Service logic]
    Service --> DB[(Database)]
    DB -->|Success| OK[Successful JSON response]
    Service -->|Domain or unexpected exception| Handler[FastAPI exception handler]
    Handler --> ErrorJSON[Standardized JSON error response]

    E422 --> RequestError[Frontend RequestError]
    ErrorJSON --> RequestError
    OK --> UI[Update UI state]

    RequestError --> Status{HTTP status}
    Status -->|401| Clear[Clear session and auth state]
    Status -->|403 or other 4xx| NoRetry[Fail without retry]
    Status -->|Transient 5xx / network failure| Retry[Retry once]
    Clear --> Show[Display error or redirect]
    NoRetry --> Show
    Retry --> Client
```

## Source alignment and limitations

- The frontend contexts, `apiClient`, React Query, FastAPI router/schema/service/model layers, SQLAlchemy, PostgreSQL, Alembic, Redis, Celery, and SMTP/IMAP adapters are taken from the supplied architecture description.
- The authentication sequence follows the supplied login and `/api/v1/auth/me` flow, including the 422 and 401 branches.
- The lifecycle diagram represents the documented TypeScript → JSON → Pydantic → service/ORM → PostgreSQL path and response path.
- The error diagram reflects the documented `RequestError`, 401 session cleanup, no retry for 401/403, one retry for transient failures, Pydantic 422 responses, and FastAPI exception handlers.
- The source describes JWT token lifecycle/session persistence, but does not specify a refresh-token endpoint or refresh-token exchange. No such flow is added here.
- These diagrams are explanatory views of the supplied document, not independent verification of implementation files.
