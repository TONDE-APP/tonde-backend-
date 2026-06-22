---
name: tonde-fastapi
description: Use this skill whenever implementing FastAPI endpoints, services, repositories, dependency injection, application architecture, middleware, validation, error handling, or any backend API feature in TONDE.
---

# TONDE — FastAPI Architecture

## Purpose

This skill defines the official FastAPI backend architecture for TONDE.

TONDE is a production SaaS B2B platform serving banks, hospitals, universities, and government institutions in Burundi, DRC, and East Africa.

Every architectural decision must prioritize:

- **Scalability** — support hundreds of institutions and millions of users
- **Maintainability** — clean code as the team grows
- **Testability** — every module must be independently testable
- **Security** — multi-tenant isolation, RBAC, zero data leaks

---

## Architecture Pattern

TONDE uses **Clean Architecture** with strict layer separation.

```
Router → Service → Repository → Database
```

**Never place business logic inside API routes.**

Each layer has one responsibility:

| Layer | Responsibility |
|---|---|
| Router | Parse request, validate input, call service, return response |
| Service | Orchestrate business logic, enforce rules |
| Repository | Execute DB queries, CRUD, filters, pagination |
| Database | PostgreSQL + Redis persistence |

---

## Project Structure

```
tonde-backend/
├── app/
│   ├── main.py                    ← FastAPI app + lifespan + router registration
│   ├── api/
│   │   └── v1/
│   │       ├── routers/
│   │       │   ├── auth.py        ← /api/v1/auth/...
│   │       │   ├── tickets.py     ← /api/v1/tickets/... + WebSocket
│   │       │   ├── branches.py    ← /api/v1/branches/...
│   │       │   ├── services.py    ← /api/v1/services/...
│   │       │   ├── counters.py    ← /api/v1/counters/...
│   │       │   └── users.py       ← /api/v1/users/...
│   │       └── dependencies/
│   │           ├── auth.py        ← get_current_user(), get_current_agent()
│   │           ├── db.py          ← get_db() session injection
│   │           └── redis.py       ← get_redis() client injection
│   ├── core/
│   │   ├── config.py              ← Settings via pydantic-settings + .env
│   │   ├── database.py            ← Async engine + AsyncSession + Base
│   │   ├── security.py            ← JWT, OTP, bcrypt, token creation
│   │   └── redis.py               ← Redis async client + helpers
│   ├── models/                    ← SQLAlchemy 2.0 ORM models
│   │   ├── user.py
│   │   ├── employee.py
│   │   ├── organization.py
│   │   ├── branch.py
│   │   ├── service.py
│   │   ├── counter.py
│   │   ├── ticket.py
│   │   └── queue_log.py
│   ├── schemas/                   ← Pydantic v2 request/response schemas
│   │   ├── auth.py
│   │   ├── ticket.py
│   │   ├── branch.py
│   │   └── common.py              ← ApiResponse, PaginatedResponse
│   ├── services/                  ← Business logic
│   │   ├── auth_service.py
│   │   ├── queue_engine.py        ← Core queue business logic
│   │   ├── ticket_service.py
│   │   ├── notification_service.py
│   │   └── analytics_service.py
│   ├── repositories/              ← Database access only
│   │   ├── ticket_repo.py
│   │   ├── branch_repo.py
│   │   └── user_repo.py
│   └── websocket/
│       ├── manager.py             ← ConnectionManager singleton
│       └── events.py              ← Event types + payloads
├── tests/
├── alembic/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env
```

---

## Routers — Rules

Routers must remain **thin**. No business logic allowed.

```python
# ✅ CORRECT — router delegates to service
@router.post("/tickets", response_model=ApiResponse[TicketResponse])
async def create_ticket(
    body: CreateTicketRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new ticket and insert into queue."""
    service = QueueEngineService(db)
    result = await service.create_ticket(body, current_user)
    return ApiResponse(success=True, data=result)

# ❌ WRONG — business logic inside router
@router.post("/tickets")
async def create_ticket(body: CreateTicketRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Ticket).where(...))  # FORBIDDEN
    ticket = Ticket(...)                                     # FORBIDDEN
    db.add(ticket)
    await db.commit()
```

---

## Services — Rules

Services contain all business logic and orchestration.

```python
# ✅ CORRECT — service handles logic, calls repository
class QueueEngineService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.ticket_repo = TicketRepository(db)

    async def create_ticket(
        self,
        data: CreateTicketRequest,
        user: User,
    ) -> TicketResponse:
        """
        Create ticket and insert into queue.

        Raises:
            HTTPException 409: duplicate active ticket
            HTTPException 400: branch closed
        """
        await self._check_no_duplicate(user.id, data.branch_id)
        await self._check_branch_open(data.branch_id)
        ticket = await self.ticket_repo.create(data, user.id)
        await self._publish_queue_event(ticket)
        return TicketResponse.model_validate(ticket)
```

---

## Repositories — Rules

Repositories access the database only. No business rules.

```python
# ✅ CORRECT — repository handles only DB access
class TicketRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: CreateTicketRequest, user_id: str) -> Ticket:
        ticket = Ticket(
            org_id=data.org_id,
            branch_id=data.branch_id,
            service_id=data.service_id,
            user_id=user_id,
            status=TicketStatus.WAITING,
            priority=data.priority,
        )
        self.db.add(ticket)
        await self.db.commit()
        await self.db.refresh(ticket)
        return ticket

    async def get_active_by_user_branch(
        self, user_id: str, branch_id: str, org_id: str
    ) -> Ticket | None:
        result = await self.db.execute(
            select(Ticket).where(
                Ticket.org_id == org_id,       # ← ALWAYS filter by org_id
                Ticket.user_id == user_id,
                Ticket.branch_id == branch_id,
                Ticket.status.in_([
                    TicketStatus.WAITING,
                    TicketStatus.CALLED,
                    TicketStatus.SERVING,
                    TicketStatus.ABSENT,
                ])
            )
        )
        return result.scalar_one_or_none()
```

---

## Schemas — Pydantic v2

Use Pydantic v2. Never expose ORM models directly.

```python
# ✅ CORRECT — Pydantic v2 schema
class CreateTicketRequest(BaseModel):
    branch_id: str
    service_id: str
    priority: TicketPriority = TicketPriority.STANDARD

    @field_validator("branch_id", "service_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError("Must be a valid UUID")
        return v

    model_config = ConfigDict(from_attributes=True)

# ❌ WRONG — Pydantic v1 syntax
class OldSchema(BaseModel):
    class Config:
        orm_mode = True  # FORBIDDEN in Pydantic v2
```

---

## Standard API Response Format

Every endpoint must return this format.

```python
# schemas/common.py
class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    message: str = "OK"

class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    code: str

# ✅ Success response
return ApiResponse(success=True, data=result, message="Ticket created")

# ✅ Error response (via HTTPException)
raise HTTPException(
    status_code=400,
    detail={"success": False, "code": "DUPLICATE_TICKET", "message": "Active ticket already exists"}
)

# ❌ WRONG — raw object returned directly
return ticket  # FORBIDDEN
```

---

## Dependency Injection

Use `Depends()`. Never instantiate dependencies inside routes.

```python
# ✅ CORRECT
@router.get("/me")
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    ...

# ❌ WRONG
@router.get("/me")
async def get_profile():
    db = AsyncSession(engine)   # FORBIDDEN — never instantiate manually
    redis = Redis(...)          # FORBIDDEN
```

---

## Async — Mandatory

TONDE is a real-time system. All code must be async.

```python
# ✅ CORRECT
async def get_ticket(ticket_id: str, db: AsyncSession) -> Ticket:
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    return result.scalar_one_or_none()

# ❌ WRONG
def get_ticket(ticket_id: str, db: Session) -> Ticket:
    return db.query(Ticket).filter(Ticket.id == ticket_id).first()  # FORBIDDEN
```

---

## API Versioning

All routes must be versioned.

```
/api/v1/auth/login
/api/v1/tickets
/api/v1/queue/call-next
```

Never modify existing v1 endpoints in a breaking way.
Add `/api/v2/` when breaking changes are required.

---

## Pagination

Required on all list endpoints.

```python
class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
```

Never return unbounded lists.

---

## Error Handling — Centralized

```python
# main.py — global exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "code": exc.detail.get("code", "ERROR"),
            "message": exc.detail.get("message", str(exc.detail)),
        },
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "code": "INTERNAL_ERROR", "message": "Internal server error"},
    )
```

Never expose stack traces in production.
Never expose internal database errors to clients.

---

## Logging — Structured

```python
import structlog

logger = structlog.get_logger()

# Log critical business events
logger.info("ticket.created", ticket_id=str(ticket.id), user_id=str(user.id), branch_id=str(ticket.branch_id))
logger.warning("auth.otp_failed", phone=phone, attempt=attempts)
logger.error("queue.engine_error", error=str(e), ticket_id=ticket_id)
```

Always log: requests, auth failures, critical events, exceptions, performance metrics.
Never log passwords, OTPs, or tokens.

---

## Documentation — OpenAPI

Every endpoint must have metadata.

```python
@router.post(
    "/tickets",
    response_model=ApiResponse[TicketResponse],
    summary="Create a new queue ticket",
    description="Creates a ticket for the authenticated user and inserts it into the branch queue.",
    responses={
        409: {"description": "Active ticket already exists"},
        400: {"description": "Branch is closed"},
    },
)
```

Swagger: `/docs`
ReDoc: `/redoc`

---

## Testing Requirements

```
85% coverage on critical modules:
  - Auth
  - Queue Engine
  - WebSocket
  - Payments (V1.5)

Required test types:
  - Unit tests (services, repositories)
  - Integration tests (API endpoints)
  - WebSocket tests
```

---

## Performance Targets

| Metric | Target |
|--------|--------|
| API P99 | < 200ms |
| Queue call action | < 100ms |
| WebSocket propagation | < 100ms P50 |
| System uptime | > 99.5% |

---

## Technical Stack

```
Python          3.12+
FastAPI         0.111.0
SQLAlchemy      2.0.x     ← async + Mapped[] style
Alembic         1.13.x    ← migrations only
Pydantic        v2        ← NEVER v1
asyncpg         0.29.x    ← PostgreSQL async driver
Redis           5.0.x     ← async aioredis
python-jose     3.3.x     ← JWT
passlib[bcrypt] 1.7.x     ← password hashing
uvicorn         0.30.x    ← ASGI server
Docker + Docker Compose   ← runtime environment
GitHub Actions            ← CI/CD
```

---

## What Must Never Happen

```
❌ Business logic inside routers
❌ Direct DB access inside routers
❌ Sync functions (def instead of async def)
❌ SQLAlchemy 1.x style (Column, Session)
❌ Pydantic v1 (orm_mode, validator without @classmethod)
❌ Queries without org_id filter on tenant data
❌ Raw ORM objects returned from routers
❌ Stack traces exposed to clients
❌ Hardcoded secrets or credentials
❌ Microservices before the monolith is stable
❌ Breaking changes to existing v1 endpoints
```

---

## Workflow Before Any Modification

```
1. Read all affected files
2. Understand the current architecture
3. Identify impact on Queue Engine and WebSocket
4. Propose a plan to Vital if it is a major change
5. Implement progressively
6. Write or update tests
7. Run: pytest + mypy + ruff
```

Never do a massive refactor without explicit validation from Vital.

---

*TONDE Backend — tonde-fastapi SKILL*
*Version 1.0 — 2026*
