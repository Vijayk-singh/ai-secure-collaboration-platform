# AI-Powered Secure Collaboration Platform

A production-grade, highly scalable collaborative backend platform built from first principles to showcase advanced distributed systems, backend engineering, software reliability, and generative AI infrastructure.

---

## Technical Stack & Infrastructure

* **Framework**: **FastAPI** (completely asynchronous ASGI web server)
* **Databases & Cache**:
  * **PostgreSQL (pgvector)**: Core relational data store, upgraded with `pgvector` for dense vector indexing.
  * **Redis**:Ephemaral cache, token revocation blacklist, active user presence sets, and Pub/Sub channel broadcasts.
* **ORM & Migrations**: **SQLAlchemy 2.0** (Async Session layers) & **Alembic** migration engine.
* **Containerization**: **Docker** & **Docker Compose** orchestrating independent, horizontally scalable API (`platform_web`) and Task Worker (`platform_worker`) service containers.
* **AI Engine**: Official **Google Gemini API** integration (`gemini-1.5-flash` completions and `text-embedding-004` vectorizations) with a deterministic local semantic vector space fallback for offline development.

---

## System Architecture

The codebase adheres to a **Strict Layered Architecture** separating routing protocols, business orchestration, database access, and background task loops:

```
                  +-----------------------------------+
                  |        Client Requests            |
                  |     (REST / WebSocket API)        |
                  +-----------------+-----------------+
                                    |
                                    v
                  +-----------------+-----------------+
                  |         Router Layer              |
                  |     (app/api/v1/endpoints/)       |
                  +-----------------+-----------------+
                                    |
                                    v
                  +-----------------+-----------------+
                  |         Service Layer             |
                  |        (app/services/)            |
                  +---------+----------------+--------+
                            |                |
                            v                v
                  +---------+------+  +------+--------+
                  | Repository Layer |  |   Task Queue  |
                  | (app/repositories|  | (Redis default|
                  +---------+------+  +------+--------+
                            |                |
                            v                v
                  +---------+------+  +------+--------+
                  |  PostgreSQL DB |  | Async Workers |
                  |   (pgvector)   |  | (app/workers/) |
                  +----------------+  +----------------+
```

### Architectural Highlights

1. **Authentication & Authorization (Level 1)**:
   * Uses asymmetric split token configurations: short-lived JWT Access Tokens paired with secure database-verified Refresh Tokens.
   * Leverages **Token Refresh Rotation (RTR)** to mitigate replay attacks and blacklists revoked tokens inside Redis caches.
   * Restricts endpoint access using **Role-Based Access Control (RBAC)** dependencies.

2. **Workspace & Paginated Notes (Level 2)**:
   * Declares scoped workspaces, membership linkages, and Tag associations.
   * Utilizes generic limit-offset pagination structures and query optimization strategies (`selectinload` / `joinedload` on SQLAlchemy relations) to prevent N+1 query bottlenecks.

3. **Horizontal Real-Time Messaging (Level 3)**:
   * Avoids scaling limitations by running an asynchronous Wildcard Redis Subscription loop (`psubscribe` to `workspace:*:room:*`). Messages sent on one node publish to Redis, which broadcasts globally across all nodes instantly.
   * Manages local socket contexts via `ConnectionManager` with bear token queries (`?token=...`) validated during WS handshakes.
   * ephemaral typing tickers and workspace presence sets are stored and broadcast directly in-memory using Redis Sets.

4. **Fault-Tolerant background Queue Loops (Level 4)**:
   * Decoupled into a standalone service container running worker loops.
   * **Atomic Delayed Scheduler**: Employs a Redis transaction pipeline (`pipeline(transaction=True)`) to check, claim, and promote ready tasks from a delayed sorted set (`queue:delayed`) to the active default queue (`queue:default`), preventing double scheduling across multi-node daemon clusters.
   * **Resilient Worker Pool**: Consumes tasks synchronously using `brpop` blocked pops, enforcing **Redis TTL Idempotency Locks** (`task:processed:{task_id}`) to prevent double executions, calculating **Exponential Backoff Retries** ($2^{\text{retry\_count}}$ seconds delay) on exceptions, and promoting failed tasks to a monitored **Dead-Letter Queue (DLQ)**.

5. **AI Vector space & Scalable RAG Pipeline (Level 5)**:
   * Incorporates an asynchronous **Recursive Character Chunker** splitting documents without clipping logical sentence structures.
   * Vectorizes markdown chunks dynamically in the background via queue pipelines, bulk inserting indices into the PostgreSQL database.
   * Builds an **HNSW vector similarity index** (`USING hnsw (embedding vector_cosine_ops)`) over chunk mappings.
   * Computes **Cosine Distance** (`NoteChunk.embedding.op("<=>")(query_vector)`) natively inside Postgres to execute Semantic Searches, feeds matched context snippets into the completion pipeline, and outputs context answers complete with source citations.
   * **Hybrid AI Engine fallback**: Uses Google's official Generative AI APIs when `GEMINI_API_KEY` is present. Otherwise, it falls back to a deterministic local semantic vector space hashing individual words into normalized unit vectors, generating similarity results with zero external dependencies!

---

## Directory Structure

```
backend/
├── alembic/                # Database baseline migrations and setup scripts
├── app/
│   ├── api/                # API Routers scoping REST / WebSocket endpoints
│   │   └── v1/
│   │       ├── deps.py     # FastAPI Security & User Extraction Dependencies
│   │       └── endpoints/  # Core endpoint routes (auth, chat, notes, etc.)
│   ├── core/               # App configuration, Database and Redis initialization
│   ├── models/             # SQLAlchemy Declarative DB models (User, Note, etc.)
│   ├── repositories/       # Base Repository patterns scoping CRUD interfaces
│   ├── schemas/            # Pydantic validation schemas (requests/responses)
│   ├── services/           # Orchestrators housing domain business logic
│   ├── websocket/          # WebSocket routers and async Broadcast Connection Managers
│   └── workers/            # Queue brokers, Scheduler Transaction daemons, Worker pools
├── scripts/                # Rigorous E2E Integration test suites
├── Dockerfile              # Unified multi-stage container configuration
└── requirements.txt        # Core application dependencies
docker-compose.yml          # Multi-service container orchestration config
README.md                   # System documentation
```

---

## API Endpoints Catalog

The platform provides a comprehensive set of REST and WebSocket endpoints. All authenticated endpoints require a standard `Authorization: Bearer <Access_Token>` HTTP header.

### 🔐 1. Authentication & Security
* `POST /api/v1/auth/register` - Registers a new user account under `MEMBER` role.
* `POST /api/v1/auth/login` - Authenticates credentials and returns a secure JWT Access/Refresh token pair.
* `POST /api/v1/auth/refresh` - Rotates expired access tokens using the stateful Token Refresh Rotation (RTR) protocol.
* `POST /api/v1/auth/logout` - Revokes refresh tokens and blacklists sessions in Redis.

### 👤 2. User Profiles & RBAC
* `GET /api/v1/users/me` - Retrieves the active user's profile details.
* `GET /api/v1/users/admin-only` - Demonstrates RBAC protection (restricts access to `ADMIN` and `OWNER` roles).

### 📁 3. Collaborative Workspaces
* `POST /api/v1/workspaces` - Creates a new workspace and automatically enrolls the creator as `OWNER`.
* `GET /api/v1/workspaces` - Lists all workspaces that the current user has joined.
* `POST /api/v1/workspaces/{workspace_id}/members` - Invites a new member to the workspace (restricted to workspace `OWNER` or `ADMIN`).
* `GET /api/v1/workspaces/{workspace_id}/members` - Lists the roster of active members and their workspace roles.

### 📝 4. Collaborative Markdown Notes
* `POST /api/v1/workspaces/{workspace_id}/notes` - Creates a note, dynamically parsing tags (triggers async background chunking and vector indexing).
* `GET /api/v1/workspaces/{workspace_id}/notes` - Lists paginated notes in the workspace, supporting full-text search string and tag filtering.
* `GET /api/v1/notes/{note_id}` - Retrieves a single note with eagerly-loaded tags.
* `PUT /api/v1/notes/{note_id}` - Edits note title or markdown content (triggers async embedding re-vectorization).
* `DELETE /api/v1/notes/{note_id}` - Deletes a note (requires note ownership or workspace owner/admin role).

### 💬 5. Real-Time Distributed Chat
* `POST /api/v1/workspaces/{workspace_id}/rooms` - Establishes a new chat room scoped inside a workspace.
* `GET /api/v1/workspaces/{workspace_id}/rooms` - Lists all chat rooms in a workspace.
* `GET /api/v1/rooms/{room_id}/messages` - Retrieves paginated historical messages for catch-up reading.
* `WS /ws/workspace/{workspace_id}/room/{room_id}?token=...` - Asynchronously handshakes, authenticates Bearer JWT query parameters, tracks online presence ephemerality, and broadcasts typing indicators and chat logs globally via wildcard Redis Pub/Sub channels.

### ⚙️ 6. Asynchronous Background Jobs
* `GET /api/v1/jobs/stats` - Audits active queue sizes (default list size, delayed sorted set size, and DLQ size).
* `GET /api/v1/jobs/dlq` - Monitors dead-lettered task payloads, failure reasons, and retry timestamps.
* `POST /api/v1/jobs/test-fail` - Simulates a failing background job to verify exponential retry backoffs and automatic DLQ promotion.

### 🤖 7. Artificial Intelligence & RAG
* `GET /api/v1/ai/search` - Searches note catalogs semantically using pgvector cosine similarity distance scans.
* `POST /api/v1/ai/rag` - Performs RAG context queries, answering questions dynamically inside the workspace with inline document citations.
* `POST /api/v1/ai/summarize-chat` - Gathers chat logs, processes transcripts, and generates a markdown bulleted digest summary highlighting active users, discussion topics, and actions.

---

## Deployment & Setup

### 1. Environment Configuration
Duplicate the configuration file and set up secret keys:
```bash
$ cp backend/.env.example backend/.env
```
Open `backend/.env` and update configuration parameters or inject your `GEMINI_API_KEY` to connect Google's official Gemini Generative models. (The system runs automatically in high-fidelity mock fallback mode if no key is supplied!).

### 2. Boot Service Containers
Use Docker Compose to build and start the multi-container stack:
```bash
$ docker compose up --build -d
```
This spawns:
* `platform_db`: PostgreSQL 16 image pre-loaded with `pgvector` extension.
* `platform_redis`: Redis 7 alpine cache broker.
* `platform_web`: FastAPI Uvicorn ASGI API server listening on `http://localhost:8000`.
* `platform_worker`: Standalone asynchronous task queue worker daemon cluster.

Verify all services are running and healthy:
```bash
$ docker compose ps
```

### 3. Run Database Migrations
Apply Alembic database migrations to establish baseline tables, pgvector extensions, and HNSW indexes:
```bash
$ docker compose exec -T web alembic upgrade head
```

---

## E2E Integration Verification

The platform includes comprehensive integration test suites checking the core business orchestration layers. Run them inside the active web container:

### Level 1: JWT Session Auth RTR & RBAC Verification
Asserts password hashing, access/refresh JWT tokens, RTR token rotation, and Role-Based Access Control:
```bash
$ docker compose exec -T web python /app/scripts/test_auth.py
```

### Level 2: Workspace Membership & Paginated Notes Verification
Tests scoped workspace creations, membership permissions, dynamic tags, and limit-offset paginated list search queries:
```bash
$ docker compose exec -T web python /app/scripts/test_workspaces.py
```

### Level 3: Distributed Real-Time WS messaging Verification
Asserts Bearer token WebSocket handshakes query parameters (`?token=...`), real-time pub/sub broadcasts, ephemeral online presence sets, and typing indicators:
```bash
$ docker compose exec -T web python /app/scripts/test_chat.py
```

### Level 4: Transactional Jobs Queue, Retries & DLQ Verification
Verifies async task queueing, transactional scheduler promotions, idempotency locks, exponential backoff delayed retries, and DLQ shunts:
```bash
$ docker compose exec -T web python /app/scripts/test_jobs.py
```

### Level 5: Scalable Vector Search & Contextual RAG Verification
Validates recursive document chunking, background worker vectorization, pgvector cosine distance database queries, context-augmented completions, and WebSocket chat summarization:
```bash
$ docker compose exec -T web python /app/scripts/test_ai.py
```
