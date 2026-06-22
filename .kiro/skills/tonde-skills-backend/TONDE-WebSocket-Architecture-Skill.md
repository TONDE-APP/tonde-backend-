# TONDE WebSocket Architecture Skill

> **Skill Name:** tonde-websocket  
> **Description:** This skill provides comprehensive guidance for implementing, modifying, debugging, and designing real-time communication within the TONDE platform. It covers FastAPI WebSockets, Redis Pub/Sub integration, connection management, queue event handling, and multi-tenant isolation.

## 1. Purpose and Business Vision

The **TONDE WebSocket Architecture** is the backbone of the platform's real-time capabilities, ensuring that the user experience remains fluid and responsive across all interfaces. In the context of high-traffic environments such as banks and hospitals, manual page refreshes are unacceptable. This architecture guarantees that all updates—from ticket calls to status changes—are pushed automatically to the relevant clients with minimal latency.

The primary business objective is to maintain a target latency of **less than 100ms (P50)** and **less than 300ms (P99)** for all event distributions. When an agent performs a critical action, such as calling a ticket or pausing a counter, every connected client within that tenant's scope must receive the update instantaneously to ensure operational efficiency and "dignified waiting."

## 2. System Architecture Overview

The real-time engine follows a decoupled, event-driven approach. Business services do not communicate directly with WebSocket clients; instead, they publish events to a **Redis Pub/Sub** layer, which acts as the central distribution hub.

| Component | Responsibility |
| :--- | :--- |
| **Queue Engine** | Processes business logic and triggers state changes. |
| **Redis Pub/Sub** | Decouples the backend services from the WebSocket gateway. |
| **WebSocket Gateway** | Manages active socket connections and filters events per tenant. |
| **Connected Clients** | Receives and renders live updates (Mobile, TV, Dashboard, Counter). |

## 3. Core Technical Components

### 3.1 Connection Manager
The `ConnectionManager` is a specialized service responsible for the lifecycle of WebSocket connections. It handles the initial handshake, tracks active sockets, manages heartbeats, and performs broadcasting with strict **tenant filtering**. By isolating this logic from the core business services, the system maintains a clean separation of concerns and improves maintainability.

### 3.2 Redis Pub/Sub Integration
Redis serves as the source of truth for event distribution. Events are published to specific channels following the pattern `institution:{id}:events`. The WebSocket gateway subscribes to these channels and forwards messages to the appropriate connected clients. This ensures that the system can scale horizontally, as any backend instance can publish an event that any gateway instance can deliver.

## 4. Official WebSocket Endpoints

The following table outlines the standardized endpoints for various client types within the TONDE ecosystem:

| Endpoint Path | Target Client | Primary Data Stream |
| :--- | :--- | :--- |
| `/ws/queue/{branch_id}` | TV Displays / Dashboard | Global branch updates and ticket calls. |
| `/ws/ticket/{ticket_id}` | Mobile Application | Individual ticket status and position updates. |
| `/ws/admin/{org_id}` | Dashboard (Future) | Organization-wide analytics and alerts. |
| `/ws/notifications` | All Clients (Future) | System-wide broadcasts and user notifications. |

## 5. Standardized Event Payloads

All events transmitted via WebSockets must be **small, typed, versioned, and formatted as JSON**. The following table defines the core event types for the MVP:

| Event Type | Key Payload Fields | Description |
| :--- | :--- | :--- |
| `TICKET_CALLED` | `ticket_id`, `display_number`, `counter_name` | Triggered when an agent calls a ticket to a counter. |
| `QUEUE_UPDATE` | `ticket_id`, `position`, `eta_minutes` | Updates the user on their current standing in the queue. |
| `TICKET_ABSENT` | `ticket_id`, `status`, `timestamp` | Marks a ticket as absent after no-show. |
| `GUICHET_STATUS` | `counter_id`, `new_status`, `timestamp` | Notifies clients when a counter opens, closes, or pauses. |
| `BROADCAST` | `message`, `severity`, `timestamp` | General messages sent by supervisors or the system. |

## 6. Security and Multi-Tenancy

**Multi-tenant isolation** is the highest priority in the TONDE architecture. A tenant must never receive events belonging to another organization. Every WebSocket connection must be authenticated via **JWT** (passed in query parameters or headers) before the handshake is completed.

Connections are strictly rejected if the token is invalid, expired, or if there is a mismatch between the user's tenant ID and the requested resource. Once connected, the `ConnectionManager` ensures that users only join channels corresponding to their authorized `organization_id` and `branch_id`.

## 7. Reliability and Performance

To ensure a robust connection, the system implements several fail-safe mechanisms:

*   **Heartbeat Management:** A ping/pong mechanism occurs every **10 seconds**; inactive sockets are automatically disconnected to free up resources.
*   **Reconnection Strategy:** Clients attempt to reconnect every **3 seconds** upon failure.
*   **Snapshot Strategy:** Upon reconnection, the server must send the **full current state** before resuming the event stream to prevent desynchronization.
*   **Offline Fallback:** If WebSocket connections fail repeatedly, the client must fallback to HTTP polling every **30 seconds** to maintain basic functionality.

## 8. Technical Stack and Future Growth

The implementation utilizes **FastAPI** with **AsyncIO** for high-concurrency handling, **Pydantic v2** for strict data validation, and **Redis** for scalable event distribution. This architecture is designed to support future integrations such as **IoT BLE Beacons**, **AI-driven wait time predictions**, and **Push Notification** synchronization without requiring a fundamental redesign of the real-time infrastructure.
