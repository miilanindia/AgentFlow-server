# 🚀 AgentFlow Backend - FastAPI Server

This repository contains the backend service for **AgentFlow**, an AI-powered Browser Automation Agent. The service is built with **FastAPI**, **PostgreSQL** (using SQLAlchemy & Alembic), **Redis**, **Celery**, and **Playwright**.

---

## 🛠️ Architecture Overview

AgentFlow uses a modern, asynchronous decoupled architecture to execute long-running browser tasks:

```mermaid
graph TD
    Client[Next.js Client] -->|HTTP Requests| FastAPI[FastAPI API Server]
    Client -->|WebSocket| WSManager[WebSocket Session Manager]
    FastAPI -->|Enqueue Task| Redis[Redis Broker]
    Redis -->|Process Job| Celery[Celery Worker]
    Celery -->|Browser Control| Playwright[Playwright Browser Engine]
    Celery -->|DB Ops| Postgres[(Neon PostgreSQL Database)]
    Celery -->|Events/Screenshots| RedisPubSub[Redis PubSub]
    RedisPubSub -->|Stream Events| WSManager
    WSManager -->|Live Frames & Timeline| Client
```

1. **FastAPI Server**: Handles client requests, user authentication, task status management, and dashboard API queries.
2. **Celery Worker**: Executes browser tasks in the background asynchronously using **Playwright** to avoid blocking the main server.
3. **Redis Broker & PubSub**: Serves as the Celery task queue broker and facilitates real-time screenshot and event streaming from the Celery worker to the client-facing WebSocket connections.
4. **PostgreSQL Database (Neon)**: Stores users, tasks, browser session metadata, timeline events, and final run outputs.

---

## 📂 Project Directory Structure

```text
AgentFlow-server/
├── app/
│   ├── agent/            # Core AI agent definitions (control loop, tool handlers)
│   ├── api/              # FastAPI Router and Endpoint controllers
│   │   └── endpoints/    # Auth, Agent execution, and Results endpoints
│   ├── browser/          # Playwright instance setup and browser context controls
│   ├── core/             # Configuration settings, logging, and security auth
│   ├── database/         # SQLAlchemy models, sessions, and base setups
│   ├── schemas/          # Pydantic schemas for request/response serialization
│   ├── services/         # Business logic (e.g., Agent Runner, LLM interfaces)
│   ├── tasks/            # Celery application setup and background tasks
│   ├── websocket/        # Real-time WebSocket connection manager and routes
│   └── main.py           # Application entry point & middleware configurations
├── alembic/              # Database migration history files
├── alembic.ini           # Alembic migration configuration
├── requirements.txt      # Python package dependencies
├── start.bat             # Windows startup helper script
└── README.md             # Project documentation
```

---

## ⚙️ Environment Configuration

Create a `.env` file in the root directory by copying the `.env.example` file:

```bash
cp .env.example .env
```

Define the following environment variables:

| Variable | Description | Example |
| :--- | :--- | :--- |
| `DATABASE_URL` | Neon PostgreSQL asynchronous connection string | `postgresql+asyncpg://user:pass@host/dbname?ssl=require` |
| `REDIS_URL` | Redis URL for Celery Broker & WebSocket PubSub | `rediss://default:token@host:port?ssl_cert_reqs=none` |
| `CORS_ORIGINS` | JSON list of origins allowed to fetch APIs (Frontend) | `["http://localhost:3000", "https://agentsflow.netlify.app"]` |
| `OPENAI_API_KEY` | OpenAI API Key (if using GPT-based models) | `sk-proj-...` |
| `GROQ_API_KEY` | Groq API Key (if using Llama/Mixtral models) | `gsk_...` |
| `DEBUG` | Boolean to enable/disable FastAPI debugger mode | `True` / `False` |
| `LOG_LEVEL` | Logging verbosity level | `INFO` / `DEBUG` / `WARNING` |

---

## 🚀 Getting Started (Local Development)

Follow these steps to set up and run the backend locally:

### 1. Set Up Virtual Environment
```bash
# Create environment
python -m venv venv

# Activate on Windows
venv\Scripts\activate

# Activate on macOS/Linux
source venv/bin/activate
```

### 2. Install Dependencies
```bash
# Install python packages
pip install -r requirements.txt

# Download required Playwright browser engines (Chromium)
playwright install chromium
```

### 3. Database Migrations
Make sure your database is up to date by running migrations with Alembic:
```bash
alembic upgrade head
```

### 4. Start the Services

You need to run **both** the FastAPI web server and the Celery worker for the application to function.

#### Option A: Run manually

* **Start FastAPI Server**:
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
  ```

* **Start Celery Worker**:
  * **On Windows** (requires `--pool=solo` to prevent multiprocessing issues):
    ```bash
    celery -A app.tasks.celery_app worker --loglevel=info --pool=solo
    ```
  * **On macOS / Linux**:
    ```bash
    celery -A app.tasks.celery_app worker --loglevel=info
    ```

#### Option B: Use Windows Helper Script
If you are on Windows, simply double-click or run:
```bash
start.bat
```
*(Note: You will need to start the Celery worker in a separate terminal using the command above).*

---

## 📡 API Reference

All REST endpoints are prefixed with `/api` by default.

### 🔑 Authentication (`/api/auth`)
* **`POST /api/auth/register`**: Creates a new user profile.
  - **Payload**: `{ "email": "user@example.com", "password": "securepassword" }`
  - **Returns**: `{ "access_token": "JWT_TOKEN", "token_type": "bearer" }`
* **`POST /api/auth/login`**: Authenticates credentials.
  - **Payload**: `{ "email": "user@example.com", "password": "securepassword" }`
  - **Returns**: `{ "access_token": "JWT_TOKEN", "token_type": "bearer" }`

### 🤖 Agent Execution & Control (`/api/agent`)
*Requires JWT Authorization header: `Bearer <token>`*
* **`POST /api/agent/start`**: Dispatches a new task execution to the Celery queue.
  - **Payload**: `{ "goal": "Find open remote software engineering jobs on foundit.in" }`
  - **Returns**: `{ "task_id": "UUID-STRING", "status": "started" }`
* **`POST /api/agent/{task_id}/pause`**: Temporarily pauses browser interactions.
* **`POST /api/agent/{task_id}/resume`**: Resumes paused browser execution.
* **`POST /api/agent/{task_id}/cancel`**: Immediately cancels the worker execution.
* **`POST /api/agent/{task_id}/approve`**: Submits user checkpoint approval to continue execution.
* **`POST /api/agent/{task_id}/reject`**: Rejects checkpoint request, ending task.

### 📊 History & Run Results (`/api/results`)
*Requires JWT Authorization header: `Bearer <token>`*
* **`GET /api/results/`**: Returns a list of all historical tasks executed by the current user.
* **`GET /api/results/{task_id}`**: Retrieves comprehensive details of a task (timeline steps, job outputs, screenshot frames, logs).

### 🔌 Live Monitoring WebSocket
* **`WS /ws/agent/{task_id}?token=JWT_TOKEN`**: Upgrades connection to WebSocket. Used by the client to receive real-time updates and screenshots from the running browser agent.

---

## 🌐 Deploying to Production (Railway)

If you are hosting this backend on **Railway**, follow these configurations:

1. **Uvicorn Start Command**:
   Set the deployment start command to:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
2. **Celery Worker Start Command**:
   Set up a separate background worker service on Railway with the start command:
   ```bash
   celery -A app.tasks.celery_app worker --loglevel=info
   ```
3. **Environment Variables**:
   Add `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY` (or `GROQ_API_KEY`), and set `CORS_ORIGINS` to match your frontend client URL (e.g. `["https://agentsflow.netlify.app"]`).
