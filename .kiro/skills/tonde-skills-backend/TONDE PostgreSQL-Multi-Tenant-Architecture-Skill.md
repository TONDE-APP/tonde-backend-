# TONDE PostgreSQL Multi-Tenant Architecture Skill

> **Skill Name:** tonde-postgresql-multitenant  
> **Description:** This skill defines the standards for designing, implementing, and maintaining the TONDE database architecture. It focuses on SaaS multi-tenancy, strict data isolation using PostgreSQL Row Level Security (RLS), and preparing the schema for future expansions like booking and mobile payments.

## 1. Core Principles and Purpose

TONDE is a multi-tenant SaaS platform serving diverse organizations such as banks, hospitals, and government administrations. The paramount requirement is **absolute data isolation**. An organization must never, under any circumstances, be able to access or even perceive the existence of another organization's data.

To achieve this, the architecture relies on a combination of:
*   **PostgreSQL Row Level Security (RLS):** Native database-level enforcement of tenant boundaries.
*   **JWT Claims:** Propagating the `org_id` from the authenticated user to the database session.
*   **Mandatory Tenant Filtering:** Explicit inclusion of `org_id` in all business-critical tables and queries.

## 2. Mandatory Data Isolation Rules

| Rule | Description | Implementation Detail |
| :--- | :--- | :--- |
| **Rule 1** | Every business-related table must contain an `org_id` column. | `org_id UUID NOT NULL` |
| **Rule 2** | No query may expose data from another organization. | Use `WHERE org_id = :current_org` or RLS. |
| **Rule 3** | Backend enforcement is mandatory. | Never trust frontend-only filtering; isolation must happen at the DB/API level. |

## 3. Core Database Schema (MVP)

### 3.1 Organization and Infrastructure
The following tables form the foundation of the multi-tenant hierarchy:

*   **`organizations`**: Stores the root entity information, subscription plans, and global settings.
*   **`branches`**: Represents physical locations (e.g., a specific bank branch) belonging to an organization.
*   **`employees`**: User accounts with roles such as `SUPER_ADMIN`, `ORG_ADMIN`, `BRANCH_ADMIN`, `SUPERVISOR`, and `AGENT`.

### 3.2 Queue Management Entities
These tables drive the core "Queue Engine" logic:

| Table | Primary Columns | Responsibility |
| :--- | :--- | :--- |
| **`services`** | `id`, `branch_id`, `name`, `avg_duration_min` | Defines the types of queues available at a branch. |
| **`counters`** | `id`, `branch_id`, `number`, `status`, `agent_id` | Represents the physical or virtual desks where service is provided. |
| **`tickets`** | `id`, `org_id`, `branch_id`, `status`, `priority`, `timestamps` | The central entity representing a customer's place in the queue. |
| **`queue_logs`** | `id`, `ticket_id`, `action`, `employee_id`, `note` | Audit trail for every action taken on a ticket. |

## 4. Performance and Optimization

### 4.1 Required Indexing Strategy
To maintain the target **API P99 < 200ms**, the following composite indexes are mandatory:
*   `(org_id, status, created_at)`: For rapid retrieval of active tickets within a tenant.
*   `(service_id, status)`: For queue length calculations per service.
*   `(counter_id, called_at)`: For agent performance and history tracking.

### 4.2 RLS Implementation Example
Row Level Security is the primary defense against data leaks. Below is the standardized policy template:

```sql
-- Enable RLS on the target table
ALTER TABLE tickets ENABLE ROW LEVEL SECURITY;

-- Create the isolation policy
CREATE POLICY tenant_isolation
ON tickets
FOR ALL
USING (
    org_id = current_setting('app.current_org')::uuid
);
```

## 5. Future-Proofing and Scalability

The schema is designed to accommodate the following modules in future versions without breaking the core architecture:

### 5.1 Appointments and Booking
Tables like `appointments` will link `user_id` and `service_id` with a `scheduled_at` timestamp, allowing the system to transition from "walk-in" only to "scheduled" service.

### 5.2 Mobile Money Payments
Integration with regional providers (Lumicash, Airtel Money, M-Pesa) will be handled via a `payments` table linked to `tickets`, tracking `amount`, `provider_ref`, and `status`.

## 6. Guidelines for AI Generation

When generating **SQLAlchemy models**, **Alembic migrations**, or **PostgreSQL schemas**, the following must be strictly preserved:
1.  **Multi-tenancy:** Always include `org_id` and ensure it is indexed.
2.  **RLS Compatibility:** Ensure all queries can work within an RLS-enabled environment.
3.  **Scalability:** Use UUIDs for primary keys to support distributed environments.
4.  **Consistency:** Use `AsyncIO` compatible drivers and patterns for the FastAPI backend.
