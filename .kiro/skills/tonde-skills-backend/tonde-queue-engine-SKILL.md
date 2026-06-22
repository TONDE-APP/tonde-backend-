---
name: tonde-queue-engine
description: Use this skill whenever implementing, modifying, testing, debugging, or designing any queue management feature in TONDE. This includes ticket creation, ticket lifecycle, priority ordering, call-next logic, ETA calculation, ticket transfers, no-show handling, ABSENT timeout, queue statistics, Redis queue acceleration, and websocket event publishing.
---

# TONDE — Queue Engine

## Purpose

This skill defines the official queue management architecture for TONDE.

**The Queue Engine is the core business component of TONDE.**

It is responsible for:

- Ticket creation and display number generation
- Priority-based ordering
- Ticket calling (call next)
- Complete ticket lifecycle management
- ETA calculation
- Duplicate ticket prevention
- WebSocket event publishing
- Audit log generation

Any modification to the Queue Engine requires a full impact analysis before implementation.

---

## Ticket State Machine

Every ticket must strictly follow this state machine.

```
                   ┌─────────┐
          ┌────────│ WAITING │────────┐
          │        └─────────┘        │
          │ (agent calls)             │ (client cancels)
          ▼                           ▼
      ┌────────┐                ┌───────────┐
      │ CALLED │                │ CANCELLED │ ← Final
      └────────┘                └───────────┘
     /    |    \
    /     |     \
   ▼      ▼      ▼
SERVING ABSENT TRANSFERRED
   |       |       |
   |   (returns)   |
   |    ▼          ▼
   |  WAITING    WAITING
   |
   ├── DONE       ← Final
   ├── INCOMPLETE ← Final
   └── TRANSFERRED
```

### Valid Transitions Table

| From | To | Triggered by |
|------|----|-------------|
| WAITING | CALLED | Agent calls next |
| WAITING | CANCELLED | Client cancels |
| CALLED | SERVING | Client presents at counter |
| CALLED | ABSENT | Timeout (3 min) with no presentation |
| CALLED | TRANSFERRED | Agent transfers |
| SERVING | DONE | Agent completes service |
| SERVING | INCOMPLETE | Agent marks incomplete |
| SERVING | TRANSFERRED | Agent transfers mid-service |
| ABSENT | WAITING | Client requests to re-enter queue |
| TRANSFERRED | WAITING | Ticket re-enters queue at target counter |

**Any transition not listed above is strictly FORBIDDEN.**

```python
# services/queue_engine.py

VALID_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.WAITING:     {TicketStatus.CALLED, TicketStatus.CANCELLED},
    TicketStatus.CALLED:      {TicketStatus.SERVING, TicketStatus.ABSENT, TicketStatus.TRANSFERRED},
    TicketStatus.SERVING:     {TicketStatus.DONE, TicketStatus.INCOMPLETE, TicketStatus.TRANSFERRED},
    TicketStatus.ABSENT:      {TicketStatus.WAITING},
    TicketStatus.TRANSFERRED: {TicketStatus.WAITING},
    TicketStatus.DONE:        set(),   # Final state
    TicketStatus.CANCELLED:   set(),   # Final state
    TicketStatus.INCOMPLETE:  set(),   # Final state
}

def validate_transition(current: TicketStatus, target: TicketStatus) -> None:
    """Raises ValueError if the transition is not allowed."""
    if target not in VALID_TRANSITIONS.get(current, set()):
        raise ValueError(
            f"Invalid transition: {current.value} → {target.value}"
        )
```

---

## Official Ticket Statuses

```python
class TicketStatus(str, Enum):
    WAITING     = "WAITING"      # In queue, waiting to be called
    CALLED      = "CALLED"       # Agent called — client must present in 3 min
    SERVING     = "SERVING"      # Client at counter, service in progress
    DONE        = "DONE"         # Service completed (final)
    ABSENT      = "ABSENT"       # Client did not present after CALLED
    TRANSFERRED = "TRANSFERRED"  # Moved to another counter/service
    CANCELLED   = "CANCELLED"    # Cancelled by client or agent (final)
    INCOMPLETE  = "INCOMPLETE"   # Service not completed (final)

# Future states (prepare Enum, do not implement logic yet):
#   SCHEDULED       ← for appointments module
#   PENDING_PAYMENT ← for payment module
#   EXPIRED         ← for appointment timeout
#   CHECKED_IN      ← for beacon/QR check-in
```

Always use the Enum. Never hardcode status strings like `"waiting"` or `"CALLED"`.

---

## Priority System

TONDE is **not a simple FIFO queue**.

```python
class TicketPriority(int, Enum):
    STANDARD  = 1   # Normal client
    VIP       = 2   # Premium subscription
    HIGH      = 3   # Pregnant, elderly, disability
    EMERGENCY = 4   # Medical emergency (hospitals only)
```

**Queue ordering:**

```sql
ORDER BY priority DESC, created_at ASC
```

Higher priority always wins.
Within the same priority level: first arrived = first served.

**Redis score formula:**

```python
import time

def compute_redis_score(priority: TicketPriority) -> float:
    """
    Score ensures priority DESC + created_at ASC ordering in Redis sorted set.
    Lower score = called first.
    """
    priority_offset = (5 - priority.value) * 1_000_000_000
    timestamp_ms = int(time.time() * 1000)
    return priority_offset + timestamp_ms
```

---

## Display Number Generation

```python
async def generate_display_number(branch_id: str, service_prefix: str, db: AsyncSession) -> str:
    """
    Generates the daily sequential ticket number.
    Resets to 1 every day at midnight.
    Format: {prefix}-{sequence}  →  B-001, B-002, ..., B-999

    Examples:
      Bank deposit   → D-001
      Bank withdrawal → R-001
      Medical consult → C-001
    """
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    count = await db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.branch_id == branch_id,
            Ticket.service_prefix == service_prefix,
            Ticket.created_at >= today_start,
        )
    )
    sequence = (count.scalar() or 0) + 1
    return f"{service_prefix}-{sequence:03d}"
```

---

## Anti-Duplicate Rule

One user cannot have more than one active ticket per branch.

Active states: `WAITING`, `CALLED`, `SERVING`, `ABSENT`, `TRANSFERRED`

```python
async def check_no_duplicate(user_id: str, branch_id: str, org_id: str, db: AsyncSession) -> None:
    """
    Raises HTTP 409 if the user already has an active ticket in this branch.
    """
    active_states = [
        TicketStatus.WAITING,
        TicketStatus.CALLED,
        TicketStatus.SERVING,
        TicketStatus.ABSENT,
        TicketStatus.TRANSFERRED,
    ]
    result = await db.execute(
        select(Ticket).where(
            Ticket.org_id == org_id,        # ← always filter by org_id
            Ticket.user_id == user_id,
            Ticket.branch_id == branch_id,
            Ticket.status.in_(active_states),
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DUPLICATE_TICKET",
                "message": "You already have an active ticket in this branch",
            }
        )
```

---

## ETA Calculation

```python
def calculate_eta(people_before: int, avg_duration_min: int) -> int:
    """
    Estimates waiting time in minutes.

    Args:
        people_before: Number of tickets ahead in queue
        avg_duration_min: Average service duration from service.avg_duration_min
                          or rolling average of last 10 completed tickets

    Returns:
        Estimated waiting time in minutes (minimum 1)
    """
    return max(1, people_before * avg_duration_min)

# Future ML-based ETA must be pluggable here without changing the interface
# The Queue Engine calls calculate_eta() — the implementation can be swapped
```

---

## Queue Engine Service — Responsibilities

```python
class QueueEngineService:
    """
    Core business service for queue management.

    All queue operations must go through this service.
    Never access ticket data directly from routers.
    """

    async def create_ticket(self, data: CreateTicketRequest, user: User) -> TicketResponse:
        """Create ticket, insert into Redis queue, publish QUEUE_UPDATE event."""

    async def call_next(self, counter_id: str, agent: Employee) -> TicketResponse:
        """
        Pop next ticket from Redis queue.
        Transition: WAITING → CALLED.
        Publish TICKET_CALLED event.
        Start 3-minute ABSENT timeout.
        """

    async def start_serving(self, ticket_id: str, agent: Employee) -> TicketResponse:
        """Transition: CALLED → SERVING."""

    async def complete_service(self, ticket_id: str, agent: Employee) -> TicketResponse:
        """Transition: SERVING → DONE. Publish QUEUE_UPDATE for all waiting tickets."""

    async def mark_absent(self, ticket_id: str, agent: Employee) -> TicketResponse:
        """
        Transition: CALLED → ABSENT.
        Call next ticket automatically.
        """

    async def transfer_ticket(self, ticket_id: str, target_counter_id: str, agent: Employee) -> TicketResponse:
        """
        Transition: CALLED|SERVING → TRANSFERRED → WAITING (at target counter).
        Publish TICKET_TRANSFERRED event.
        """

    async def cancel_ticket(self, ticket_id: str, user: User) -> None:
        """Transition: WAITING → CANCELLED. Remove from Redis queue."""

    async def return_from_absent(self, ticket_id: str, agent: Employee) -> TicketResponse:
        """Transition: ABSENT → WAITING. Re-insert into Redis queue."""

    async def get_queue_status(self, branch_id: str, org_id: str) -> QueueStatusResponse:
        """Return current queue state for a branch (used by TV display and dashboard)."""
```

---

## Redis Queue Integration

Redis accelerates queue operations. PostgreSQL is the source of truth.

```python
# Redis key structure
QUEUE_KEY = "queue:{org_id}:{branch_id}:{service_id}"  # Sorted Set

# Add ticket to queue
score = compute_redis_score(ticket.priority)
await redis.zadd(QUEUE_KEY, {str(ticket.id): score})

# Get next ticket (lowest score = highest priority + oldest)
next_ids = await redis.zrange(QUEUE_KEY, 0, 0)
next_ticket_id = next_ids[0] if next_ids else None

# Remove ticket from queue (after called or cancelled)
await redis.zrem(QUEUE_KEY, str(ticket_id))

# Get position in queue
position = await redis.zrank(QUEUE_KEY, str(ticket_id))
# position is 0-indexed, add 1 for display

# Get queue size
size = await redis.zcard(QUEUE_KEY)
```

Redis is the cache. PostgreSQL stores the canonical state.
If Redis is unavailable, fall back to PostgreSQL query with ORDER BY priority DESC, created_at ASC.

---

## WebSocket Event Publishing

The Queue Engine **publishes events**. The WebSocket Manager **broadcasts** them.
Never send events directly from Queue Engine to clients.

```python
async def _publish_event(self, event_type: str, payload: dict, org_id: str, branch_id: str) -> None:
    """Publish event to Redis Pub/Sub channel."""
    channel = f"org:{org_id}:branch:{branch_id}:events"
    event = {
        "type": event_type,
        "payload": payload,
        "org_id": org_id,
        "branch_id": branch_id,
        "timestamp": datetime.utcnow().isoformat(),
    }
    await redis.publish(channel, json.dumps(event))

# Events published by Queue Engine
TICKET_CREATED   → after successful ticket creation
TICKET_CALLED    → after call_next
QUEUE_UPDATE     → position/ETA update for all waiting tickets
TICKET_ABSENT    → after mark_absent
TICKET_TRANSFERRED → after transfer
TICKET_DONE      → after complete_service
QUEUE_STATUS     → full queue snapshot (for reconnecting clients)
```

---

## Audit Logging

Every state transition must be logged to `queue_logs`.

```python
async def _log_action(
    self,
    ticket_id: str,
    from_status: TicketStatus,
    to_status: TicketStatus,
    employee_id: str | None,
    note: str | None,
) -> None:
    log = QueueLog(
        ticket_id=ticket_id,
        action=f"{from_status.value}→{to_status.value}",
        employee_id=employee_id,
        note=note,
        created_at=datetime.utcnow(),
    )
    self.db.add(log)
    await self.db.flush()
```

---

## Performance Targets

| Operation | Target |
|-----------|--------|
| Call next ticket | < 100ms |
| Create ticket | < 150ms |
| WebSocket event propagation | < 100ms P50 |
| API P99 (all queue endpoints) | < 200ms |
| Redis queue operations | < 10ms |

---

## What Must Never Happen

```
❌ Ticket state transition not in VALID_TRANSITIONS
❌ Status strings hardcoded ("waiting", "CALLED") — use Enum
❌ Business logic inside routers
❌ Direct Redis or DB access from routers
❌ Duplicate tickets for the same user in same branch
❌ ETA calculated on the client side
❌ WebSocket events sent directly from Queue Engine (must go through Redis Pub/Sub)
❌ Queue log missing for any state transition
❌ org_id missing from any query
❌ Queue operations without Redis fallback to PostgreSQL
```

---

## Future Compatibility

Prepare for these states without implementing logic yet:

```python
# Add to TicketStatus enum (prepare only)
SCHEDULED       = "SCHEDULED"        # Appointment module (V1.5)
PENDING_PAYMENT = "PENDING_PAYMENT"  # Payment module (V1.5)
EXPIRED         = "EXPIRED"          # Appointment timeout (V1.5)
CHECKED_IN      = "CHECKED_IN"       # BLE Beacon check-in (V2.0)
```

Design transitions to accommodate these without breaking existing code.

---

*TONDE Backend — tonde-queue-engine SKILL*
*Version 1.0 — 2026*
