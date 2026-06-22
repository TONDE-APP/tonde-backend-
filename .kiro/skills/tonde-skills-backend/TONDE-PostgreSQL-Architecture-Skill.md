# TONDE PostgreSQL Architecture Skill

> **Skill Name:** tonde-postgresql  
> **Description:** This skill provides the definitive guide for designing, modifying, querying, and optimizing the TONDE PostgreSQL database. It covers the multi-tenant data model, Row Level Security (RLS), composite indexing strategies, SQLAlchemy 2.0 standards, and migration workflows with Alembic.

## 1. Architectural Vision and Core Principles

The TONDE database is designed as a high-performance, multi-tenant SaaS foundation capable of serving banks, hospitals, universities, and government institutions across Africa. The core architectural principle is that **every piece of business data must have clear organization ownership**.

*   **Tenant Isolation:** Guaranteed through multi-layered security (API, Services, and DB-level RLS).
*   **Scalability:** Optimized for high-concurrency queue operations and future regional expansion.
*   **Maintainability:** Strict adherence to modern ORM standards and migration protocols.

## 2. Multi-Tenant Data Hierarchy

Data in TONDE flows through a strict ownership hierarchy to ensure logical separation and performance:

1.  **Organization:** The root entity (the customer).
2.  **Branch:** Physical agencies belonging to an organization.
3.  **Service:** Specific types of queues offered at a branch.
4.  **Counter:** The physical or virtual desk where services are delivered.
5.  **Ticket:** The primary transactional unit representing a customer's journey.

## 3. Core Database Entities (MVP)

| Table | Key Fields | Description |
| :--- | :--- | :--- |
| **`organizations`** | `id`, `name`, `plan`, `created_at` | Root customer data. |
| **`branches`** | `id`, `org_id`, `name`, `location`, `timezone` | Agency infrastructure. |
| **`employees`** | `id`, `org_id`, `branch_id`, `role`, `pin_hash` | Staff and administrative accounts. |
| **`users`** | `id`, `phone`, `email`, `lang_pref` | Mobile customers (Global/Local). |
| **`services`** | `id`, `branch_id`, `name`, `avg_duration_min` | Branch-specific queue types. |
| **`counters`** | `id`, `branch_id`, `number`, `status`, `agent_id` | Physical service points. |
| **`tickets`** | `id`, `org_id`, `branch_id`, `service_id`, `status` | The heart of the queue engine. |
| **`queue_logs`** | `id`, `ticket_id`, `action`, `employee_id`, `note` | Full audit trail for every ticket action. |

## 4. Security and Data Integrity Standards

### 4.1 Row Level Security (RLS)
RLS is the final and most critical layer of protection. Every organization must only access its own data. While FastAPI performs initial filtering, RLS ensures that no database session can leak data across tenant boundaries.

### 4.2 UUID Policy
To prevent data enumeration and simplify distributed systems, **UUID v4** is mandatory for all primary keys. Sequential integer IDs must never be exposed via public APIs.

### 4.3 Soft Delete and Auditability
*   **Soft Deletes:** Use `deleted_at` timestamps instead of physical row deletion to preserve historical data.
*   **Traceability:** Every critical action (ticket creation, transfer, completion, role changes) must be logged with precise timestamps.

## 5. Implementation and Performance Standards

### 5.1 SQLAlchemy 2.0 Standards
All Python-based database interactions must use modern SQLAlchemy 2.0 syntax:
*   Use `Mapped[]` and `mapped_column()` for type-safe models.
*   Avoid legacy `Column` and `relationship` syntax.
*   Ensure all models are fully typed for better developer experience and reliability.

### 5.2 Indexing Strategy
Performance is treated as a product feature. The following composite indexes are required:
*   `tickets`: `(org_id, status, created_at)`, `(service_id, status)`, `(counter_id, called_at)`.
*   `users`: `(phone)`, `(email)`.
*   `employees`: `(org_id, role)`.

### 5.3 Alembic Migration Workflow
Direct manual edits to the production schema are strictly forbidden. The standardized workflow is:
`Define Model` → `Generate Alembic Revision` → `Review Migration` → `Apply/Deploy`.

## 6. Performance Targets

| Metric | Target Value |
| :--- | :--- |
| **Database Throughput** | 500+ requests per second |
| **Hot Query Latency** | < 100ms |
| **API P99 Latency** | < 200ms |
| **Queue Operations** | < 100ms |

## 7. Future Compatibility
The current schema is designed to be "non-blocking" for future modules, including:
*   **Booking & Appointments:** Scheduled service integration.
*   **Mobile Money:** Lumicash, Airtel Money, and M-Pesa payment tracking.
*   **AI Predictions:** Training data for wait-time estimations.
*   **Ratings & Feedback:** Post-service customer satisfaction metrics.
