---
name: tonde-auth-jwt
description: Use this skill whenever implementing authentication, authorization, OTP verification, JWT tokens, RBAC permissions, user sessions, refresh tokens, mobile login, employee login, role checking, or any security feature in TONDE.
---

# TONDE — Authentication & Authorization

## Purpose

This skill defines the official authentication and authorization system of TONDE.

TONDE serves banks, hospitals, universities, and government institutions.
Security must be enterprise-grade from day one.

The system must support:

- **Mobile users** (CLIENT) — phone + OTP
- **Agents** (AGENT) — PIN or email + password
- **Supervisors** (SUPERVISOR)
- **Branch admins** (ADMIN_BRANCH)
- **Organization admins** (ADMIN_ORG)
- **Super admins** (SUPER_ADMIN) — Vital + Tonde team

Future integrations to prepare for (without implementing now):

- Google OAuth
- Facebook OAuth
- Biometric login (fingerprint, Face ID)
- Enterprise SSO

---

## Authentication Strategy

TONDE uses **dual JWT** — Access Token + Refresh Token.

```
Access Token  → short-lived  → 15 minutes
Refresh Token → long-lived   → 7 to 30 days

Never use single-token strategy.
Never use sessions stored in memory on the server.
```

---

## Login Methods

### Mobile User (CLIENT)

```
POST /api/v1/auth/register/phone
  Body: { phone, country_code }
  Action: send OTP via Africa's Talking SMS

POST /api/v1/auth/verify/otp
  Body: { phone, otp }
  Action: verify OTP → generate access_token + refresh_token + user profile

Development: OTP is always "123456"
```

### Employee (AGENT, SUPERVISOR, ADMIN)

```
POST /api/v1/auth/login
  Body: { email, password }
  Action: verify bcrypt hash → generate tokens

Future:
POST /api/v1/auth/login/google
POST /api/v1/auth/login/facebook
```

---

## JWT Claims

Every Access Token must contain these claims.

```json
{
  "sub": "user-uuid",
  "role": "AGENT",
  "org_id": "org-uuid",
  "branch_id": "branch-uuid",
  "token_type": "access",
  "exp": 1735000000,
  "iat": 1734999100
}
```

```python
# security.py
def create_access_token(user: User | Employee) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "org_id": str(user.org_id),
        "branch_id": str(getattr(user, "branch_id", None)),
        "token_type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")

def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "token_type": "refresh",
        "exp": datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
```

---

## RBAC — Roles and Permissions

```python
class UserRole(str, Enum):
    CLIENT      = "CLIENT"       # Mobile user — take tickets, pay, evaluate
    AGENT       = "AGENT"        # Counter agent — call next, manage counter
    SUPERVISOR  = "SUPERVISOR"   # Branch supervisor — view stats, manage agents
    ADMIN_BRANCH = "ADMIN_BRANCH" # Branch admin — configure services, reports
    ADMIN_ORG   = "ADMIN_ORG"    # Org admin — manage all branches
    SUPER_ADMIN = "SUPER_ADMIN"  # Tonde team — full access
```

**Role-based permissions:**

| Action | CLIENT | AGENT | SUPERVISOR | ADMIN_BRANCH | ADMIN_ORG | SUPER_ADMIN |
|--------|--------|-------|------------|--------------|-----------|-------------|
| Create ticket | ✅ | — | — | — | — | ✅ |
| Call next | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| Mark absent | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| View branch stats | — | — | ✅ | ✅ | ✅ | ✅ |
| Manage agents | — | — | — | ✅ | ✅ | ✅ |
| Configure services | — | — | — | ✅ | ✅ | ✅ |
| Manage org | — | — | — | — | ✅ | ✅ |

---

## Dependency Injection — Auth Guards

```python
# api/v1/dependencies/auth.py

bearer_scheme = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validates JWT and returns the authenticated user. Raises 401 if invalid."""
    token = credentials.credentials
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "Token invalid or expired"}
        )
    user = await UserRepository(db).get_by_id(payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail={"code": "USER_NOT_FOUND", "message": "User not found"}
        )
    return user

async def get_current_agent(
    current_user: User = Depends(get_current_user),
) -> User:
    """Requires AGENT, SUPERVISOR, ADMIN_BRANCH, ADMIN_ORG, or SUPER_ADMIN role."""
    allowed = {UserRole.AGENT, UserRole.SUPERVISOR, UserRole.ADMIN_BRANCH, UserRole.ADMIN_ORG, UserRole.SUPER_ADMIN}
    if current_user.role not in allowed:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "Agent role required"}
        )
    return current_user

async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Requires ADMIN_BRANCH, ADMIN_ORG, or SUPER_ADMIN role."""
    allowed = {UserRole.ADMIN_BRANCH, UserRole.ADMIN_ORG, UserRole.SUPER_ADMIN}
    if current_user.role not in allowed:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "Admin role required"}
        )
    return current_user
```

---

## Multi-Tenant Security

TONDE is multi-tenant. Every authenticated user belongs to one `org_id`.

Security must be enforced at **all three layers**:

```
API Layer        → check role via Depends()
Service Layer    → filter by org_id in every query
Database Layer   → PostgreSQL RLS as final guard
```

```python
# ✅ CORRECT — always enforce org_id isolation
async def get_branch(branch_id: str, current_user: User) -> Branch:
    result = await db.execute(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.org_id == current_user.org_id,  # ← MANDATORY
        )
    )
    branch = result.scalar_one_or_none()
    if not branch:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Branch not found"})
    return branch

# ❌ WRONG — missing org_id filter allows cross-tenant data leak
async def get_branch(branch_id: str) -> Branch:
    result = await db.execute(select(Branch).where(Branch.id == branch_id))  # FORBIDDEN
```

---

## OTP Rules

```python
OTP_LENGTH        = 6          # digits only
OTP_EXPIRE_MIN    = 5          # minutes → stored as Redis TTL
OTP_MAX_ATTEMPTS  = 3          # after 3 failures → block
OTP_BLOCK_MIN     = 30         # minutes blocked after max failures
OTP_RESEND_COOLDOWN = 60       # seconds before resend is allowed

# In development: always accept "123456"
DEV_OTP = "123456"

# Storage: Redis with TTL
# Key:   otp:{phone}       → hashed OTP
# Key:   otp_attempts:{phone} → integer counter
# Key:   otp_blocked:{phone}  → block flag

# ✅ CORRECT — never store OTP in plain text
import hashlib
hashed_otp = hashlib.sha256(otp.encode()).hexdigest()
await redis.setex(f"otp:{phone}", OTP_EXPIRE_MIN * 60, hashed_otp)

# ❌ WRONG — plain text OTP in Redis
await redis.setex(f"otp:{phone}", 300, otp)  # FORBIDDEN
```

---

## Refresh Token Rules

```python
# Refresh tokens are stored in the database (revocable)
# Access tokens cannot be revoked (short lifetime)

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str]        # hashed, never plain
    device_id: Mapped[str | None]  # device awareness
    ip_address: Mapped[str | None]
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]

# On logout → set revoked_at = now()
# On login from new device → create new refresh token
# Multiple active sessions allowed (multi-device)
```

---

## Password Rules

```python
# Minimum: 8 characters
# Must contain: uppercase, lowercase, digit
# Hash with: bcrypt (passlib)
# Never store plain text
# Never log passwords

from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
```

---

## Rate Limiting

```
Authenticated users       → 30 requests/minute
Login failures            → 10 attempts before temporary block
OTP failures              → 3 attempts before 30-minute block
OTP resend                → 1 request per 60 seconds
Exceeded limits           → HTTP 429 Too Many Requests
```

---

## Required API Endpoints

```
POST /api/v1/auth/register/phone    → Send OTP SMS
POST /api/v1/auth/verify/otp        → Verify OTP → JWT
POST /api/v1/auth/register/email    → Email registration
POST /api/v1/auth/login             → Email + password → JWT
POST /api/v1/auth/refresh           → Refresh token → new access token
POST /api/v1/auth/logout            → Revoke refresh token
POST /api/v1/auth/resend-otp        → Resend OTP (60s cooldown)
GET  /api/v1/auth/me                → Current user profile

Future (prepare architecture, do not implement now):
POST /api/v1/auth/login/google
POST /api/v1/auth/login/facebook
POST /api/v1/auth/login/biometric
```

---

## Audit Logging

All security events must be logged to `audit_logs`.

```python
# Events to log
EVENTS = [
    "auth.login_success",
    "auth.login_failure",
    "auth.logout",
    "auth.otp_sent",
    "auth.otp_verified",
    "auth.otp_failed",
    "auth.token_refreshed",
    "auth.password_changed",
    "auth.role_changed",
]

# Fields to store
{
    "event": "auth.login_failure",
    "user_id": "...",      # nullable if unknown user
    "ip": "...",
    "user_agent": "...",
    "timestamp": "...",
    "org_id": "...",
}

# Never log: passwords, OTP codes, JWT tokens
```

---

## Session Management

```python
# Support multiple devices, multiple active sessions
# Each session tracks:
{
    "session_id": "uuid",
    "user_id": "uuid",
    "device_id": "...",
    "created_at": "...",
    "last_seen": "...",
    "ip_address": "...",
}

# Future admin dashboard feature:
# - View all active sessions
# - Terminate specific session
# - Terminate all sessions (global logout)
```

---

## What Must Never Happen

```
❌ Single JWT strategy (no refresh token)
❌ OTP stored in plain text
❌ Passwords stored in plain text
❌ Role checks done only on the frontend
❌ Missing org_id filter in queries
❌ Passwords or tokens logged
❌ Stack traces exposed to clients
❌ Access tokens revoked (they expire, use refresh tokens for revocation)
❌ Refresh tokens stored in plain text in DB
❌ Same OTP accepted twice (delete after verification)
```

---

## Security Goal

```
OWASP Top 10 compliant
Multi-tenant secure — zero cross-tenant data access
Enterprise-ready — supports SSO, OAuth, biometrics in the future
Production-ready — bcrypt, HTTPS, rate limiting, audit logs
```

---

*TONDE Backend — tonde-auth-jwt SKILL*
*Version 1.0 — 2026*
