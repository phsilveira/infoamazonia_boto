# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

InfoAmazonia Boto is a FastAPI application powering a WhatsApp chatbot (`BOTO`) that delivers personalized news, article discovery, and analytics for the Brazilian Amazon region. The service orchestrates PostgreSQL (with pgvector), Redis, OpenAI/Azure OpenAI, and external content APIs.

### Key Features
- **WhatsApp chatbot** with stateful flows and message templates (state machine via `transitions` library)
- **Hybrid search** combining vector embeddings (pgvector) and full-text queries
- **Admin portal** for managing sources, messages, scheduled digests, and analytics
- **Background jobs** (APScheduler) for ingestion, newsletters, and cleanup in São Paulo timezone

## Development Setup

### Prerequisites
- Python 3.11+
- PostgreSQL 14+ with `pgvector` extension
- Redis 6+
- Docker & Docker Compose (optional but recommended)

### Quick Start

```bash
# 1. Install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -e .

# 2. Configure environment
cp .env.development .env  # or create .env with required keys
# Required keys: DATABASE_URL, REDIS_HOST, REDIS_PORT, OPENAI_API_KEY (or Azure equivalents)
# See config.py for all available settings

# 3. Prepare database
python scripts/reset_database.py   # Drops and recreates schema + pgvector extension
python scripts/create_admin.py      # Creates default admin user

# 4. Run development server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 5. Access the application
# API docs: http://localhost:8000/docs
# Admin portal: http://localhost:8000/admin (login required)
```

### Using Docker Compose

For local development with PostgreSQL and Redis pre-configured:

```bash
docker compose up --build

# Run admin scripts inside the container
docker compose exec app python reset_database.py
docker compose exec app python create_admin.py
```

The Docker setup uses:
- `ankane/pgvector` image with Postgres 16 (credentials: boto/boto)
- `redis:7-alpine` with automatic persistence
- FastAPI app (port 8000) with health checks

## Common Commands

### Development

```bash
# Start development server (with auto-reload)
uvicorn main:app --reload

# Run ChatGPT integration tests (covers both OpenAI and Azure)
python scripts/test_chatgpt_service.py

# For Azure OpenAI testing:
USE_AZURE_OPENAI=True python scripts/test_chatgpt_service.py

# Seed analytics data for testing
python scripts/insert_fake_interactions.py

# Create a database dump
python scripts/dump_database.py --output backups/boto_dump.sql
```

### Database Management

```bash
# Full reset (drops schema, recreates with pgvector enabled)
python scripts/reset_database.py

# Create/reset admin user
python scripts/create_admin.py

# Backup database
python scripts/dump_database.py postgresql://user:pass@host/dbname
```

### Docker Operations

```bash
# Build and start all services
docker compose up --build

# Run specific admin script in container
docker compose exec app python reset_database.py

# Stop and remove all containers
docker compose down

# Stop and remove containers + volumes (careful!)
docker compose down -v
```

### Azure Deployment

```bash
# Initialize environment
azd init --template .
azd env new <env-name>

# Set secrets and credentials (preferred over hard-coding)
azd env set OPENAI_API_KEY "your-key"
azd env set POSTGRES_ADMIN_PASSWORD "secure-password"
# ... repeat for WHATSAPP_*, MAILGUN_*, etc.

# Automated secret sync from .env file
python scripts/sync_env_to_azd.py --env-file .env --environment dev

# Provision Azure resources + deploy
azd up

# Update code only
azd deploy

# Check deployed app
azd show
```

## Architecture Overview

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         FASTAPI APP                             │
│  (main.py - entry point, routers, lifecycle management)         │
└─────────────────────────────────────────────────────────────────┘
         │                    │                      │
         ▼                    ▼                      ▼
   ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
   │    ADMIN     │  │   WEBHOOK    │  │   API ENDPOINTS  │
   │ Portal       │  │   Handler    │  │   (/api/search)  │
   │ (admin/*)    │  │ (webhook.py) │  │ (api_endpoints)  │
   └──────────────┘  └──────────────┘  └──────────────────┘
         │                    │                      │
         └────────┬───────────┴──────────────────────┘
                  ▼
      ┌───────────────────────────┐
      │   CORE SERVICES           │
      │  (services/ directory)    │
      │ - chatbot (state machine) │
      │ - chatgpt (OpenAI/Azure)  │
      │ - search (hybrid queries) │
      │ - whatsapp (send_message) │
      │ - handlers (state logic)  │
      │ - email, location, etc.   │
      └───────────────────────────┘
         │              │              │
         ▼              ▼              ▼
    ┌─────────┐  ┌──────────┐  ┌──────────┐
    │PostgreSQL  │  Redis     │  External │
    │+ pgvector  │  (caching) │  APIs     │
    │(SQLAlchemy)│  (sessions)│           │
    └─────────┘  └──────────┘  └──────────┘
```

### Directory Structure & Responsibilities

| Directory | Purpose |
|-----------|---------|
| `admin/` | Admin portal routers (users, news_sources, messages, articles, metrics, scheduler). Includes dashboard templates & cache invalidation helpers. |
| `services/` | Domain logic: chatbot, chatgpt, search, article_ingestion, handlers (state-specific chatbot logic), whatsapp, email, location, embeddings. |
| `routers/` | Public API endpoints (location, article, ingestion). |
| `utils/` | Utility helpers: message_loader (loads messages.yml), prompt_loader (loads prompts.yml), url_detector. |
| `templates/` | Jinja2 templates for admin UI. |
| `static/` | CSS, JavaScript, and other static assets. |
| `infra/` | Bicep infrastructure-as-code for Azure deployments (App Service, PostgreSQL Flexible Server, Cache for Redis). |
| `scripts/` | CLI utilities: reset_database.py, create_admin.py, dump_database.py, sync_env_to_azd.py, test_chatgpt_service.py. |
| `docs/` | Documentation: MAINTAINERS.md (detailed ops guide), API_DOCUMENTATION.md, replit.md. |

### Data Models (SQLAlchemy ORM)

Key entities in `models.py`:
- **User**: phone_number, name, schedule (daily/weekly/monthly), is_active
- **UserPreference**: notification_frequency, topics per user
- **Article**: UUID primary key, title, content, embedding (Vector 1536), metadata, pgvector IVFFLAT index for similarity search
- **Message**: WhatsApp message logs with status tracking
- **UserInteraction**: Tracks chatbot interactions (term queries, article summaries, feedback)
- **NewsSource**: Feed URLs for ingestion
- **Admin**: Portal login credentials (username, hashed password, role)
- **SchedulerRun**: Background job execution logs
- **ScheduledMessage**: Template-based bulk message scheduling

### Authentication & Session Management

- **Admin Portal**: JWT tokens (jose library) + Jinja template sessions
- **Chatbot State**: Stored in Redis (`processing:{phone}`, `state:{phone}`) to track conversation flow
- **Password Resets**: Tokens stored in Redis with TTL (`reset:{token}`)
- **Caching**: Redis-backed cache with `get_cache()`, `set_cache()`, `invalidate_cache()` helpers

## Request Flows

### 1. WhatsApp Chatbot (Stateful Conversation)

```
Meta Webhook Callback
  ↓
webhook.py: @router.post("/webhook")
  ↓
verify webhook signature
  ↓
process_webhook_message(phone, message_content)
  ↓
Load/create ChatBot instance (transitions state machine)
  ↓
Determine state → Call handler from services/handlers.py
  ↓
Handler may call:
  - ChatGPTService (summarize, explain terms)
  - services/search.py (find articles)
  - services/whatsapp.send_message()
  ↓
Update Redis state + database
  ↓
Return response to Meta API
```

**State Machine States** (from `services/chatbot.py`):
`start`, `register`, `menu_state`, `modify_subscription_state`, `get_user_location`, `get_user_subject`, `get_user_schedule`, `about`, `get_term_info`, `get_article_summary`, `get_news_suggestion`, `feedback_state`, `unsubscribe_state`, `process_url_state`, `select_url_state`

### 2. Admin Portal (CRUD with Cache Invalidation)

```
Browser → FastAPI admin router (e.g., admin/users.py)
  ↓
Authenticate with JWT + get_current_admin_dependency()
  ↓
SQLAlchemy CRUD operations
  ↓
Call invalidate_dashboard_caches() after writes
  ↓
Render Jinja2 template with updated data
  ↓
Return HTML response
```

### 3. Search & Analytics APIs

```
GET /api/search?query=...
  ↓
api_endpoints.py handler
  ↓
Call services/search.py async helper (search_articles_service, get_article_stats_service, etc.)
  ↓
Hybrid query:
  - Generate embedding for query (OpenAI)
  - pgvector cosine similarity search
  - Full-text search fallback
  - Combine results, apply filters
  ↓
Cache result in Redis (@cached decorator)
  ↓
Return JSON response
```

### 4. Background Jobs (APScheduler)

```
Application startup (lifespan hook in main.py)
  ↓
scheduler.py: start_scheduler()
  ↓
Register jobs (send_daily_news, send_weekly_news, ingest_articles, cleanup_old_messages)
  ↓
Jobs run on cron schedule (São Paulo timezone)
  ↓
Each job:
  - Logs execution to SchedulerRun table
  - Sends WhatsApp messages to subscribed users
  - Handles failures gracefully
  ↓
Logs visible in admin/scheduler.py dashboard
```

## Configuration & Environment Variables

All settings loaded from `.env` file via `config.py` (Pydantic BaseSettings):

### Database
- `DATABASE_URL`: PostgreSQL connection string (required)
- Or individual `PG*` variables (handled by Azure)

### Redis
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` (default: localhost:6379)
- `REDIS_PASSWORD`: Optional
- `REDIS_USE_TLS`: Set to `true` for Azure Cache (enforced TLS 1.2)

### OpenAI / Azure OpenAI
- **Standard OpenAI**: Set `OPENAI_API_KEY`
- **Azure OpenAI**: Set `USE_AZURE_OPENAI=True` + `AZURE_OPENAI_API_KEY`, `ENDPOINT_URL`, `DEPLOYMENT_NAME`, `AZURE_API_VERSION`
- Note: `services/location` always uses standard OpenAI SDK; provide `OPENAI_API_KEY` even if using Azure for other services

### WhatsApp & External Services
- `WHATSAPP_API_URL`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`
- `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`
- `GOOGLEMAPS_API_KEY`
- `HOST_URL`: Base URL for short link redirects (e.g., https://boto.infoamazonia.org/)

### Security & Logging
- `SECRET_KEY`: JWT secret for admin sessions
- `WEBHOOK_VERIFY_TOKEN`: Meta webhook verification token
- `LOG_LEVEL`: INFO, DEBUG, WARNING, ERROR
- `ENV`: development or production

## Key Implementation Patterns

### 1. Async/Await & SQLAlchemy Sessions

```python
# In FastAPI endpoints, accept Session dependency:
async def my_endpoint(db: Session = Depends(get_db)):
    # Use db for queries
    user = db.query(models.User).filter(...).first()
```

### 2. Caching with @cached Decorator

```python
@cached(expire_seconds=300, prefix="my_cache")
async def expensive_endpoint(request: Request, db: Session = Depends(get_db)):
    # Automatic Redis caching; falls back gracefully if Redis unavailable
```

### 3. Loading YAML Copy & Prompts

```python
# messages.yml is loaded via singleton:
from utils.message_loader import message_loader
copy = message_loader.get_message("menu.main")

# prompts.yml is loaded via singleton:
from utils.prompt_loader import prompt_loader
prompt = prompt_loader.get_prompt("gpt-4.article_summary")
```

### 4. Chatbot State Transitions

```python
# In handlers, trigger state changes:
bot = ChatBot(db, redis_client)
if some_condition:
    bot.show_menu()  # Triggers transition to 'menu_state'
```

### 5. Search with Embeddings

```python
# From services/search.py:
articles = await search_articles_service(
    query="term",
    use_embeddings=True,
    normalize_embeddings=True
)
# Combines pgvector similarity + full-text fallback
```

### 6. URL Shortening & CTR Tracking

```python
# From services/search.py:
short_url = await shorten_url_async(full_url, base_url, redis_client=redis_client)

# Metrics stored in Redis; retrieved via get_ctr_stats_service()
# Redirects handled by /r/{short_id} route in main.py
```

## Maintenance & Operational Notes

### Graceful Degradation
- If Redis is unavailable, caching & session state degrade gracefully (but chatbot state tracking may be affected)
- Missing API keys (Mailgun, Twilio, etc.) are logged but don't crash the app
- Search falls back to full-text if embeddings unavailable

### Cache Invalidation
After admin writes (user updates, source changes, message edits), call:
```python
from cache_utils import invalidate_dashboard_caches
await invalidate_dashboard_caches()  # Clears analytics cards in admin UI
```

### Database Connection Pool
- Configured with `QueuePool` (size=5, max_overflow=10, recycle=1800s)
- Keepalives + timeouts for long-lived connections
- `pool_pre_ping=True` to detect stale connections

### Scheduler Timezone
All APScheduler jobs run in São Paulo timezone (`America/Sao_Paulo`). When adding new jobs:
```python
# In scheduler.py's start_scheduler():
scheduler.add_job(my_job, CronTrigger(hour=9, minute=0, timezone=SP_TIMEZONE), id='my_job')
```

### Azure Deployment Notes
- Bicep templates in `infra/` provision App Service + PostgreSQL Flexible Server + Cache for Redis
- `WEBSITES_PORT=8000` is set automatically
- Secrets are synced via `azd env set` (preferred over hardcoding in `infra/main.parameters.json`)
- Use `sync_env_to_azd.py` to automate secret population from `.env`

### URL Shortener Storage Format
The `/r/{short_id}` redirect route shares storage with `services/search.py` helpers. If changing key formats, update both sides:
- Route handler in `main.py`
- `_store_url_in_redis_async()` and `_store_url_in_memory_cache()` in `services/search.py`

## Testing & Validation

### Unit Testing
No formal test suite exists yet, but the script-based approach is used:

```bash
# Test ChatGPT integration (both OpenAI and Azure)
python scripts/test_chatgpt_service.py

# For Azure:
USE_AZURE_OPENAI=True python scripts/test_chatgpt_service.py
```

### Manual Testing
- **Chatbot flows**: Simulate inbound WhatsApp messages against `/webhook` endpoint
- **Search endpoints**: Hit `/api/search`, `/api/article-stats`, `/api/ctr-stats` with auth cookie
- **Admin portal**: Test CRUD operations, verify cache invalidation
- **Background jobs**: Check `admin/scheduler.py` dashboard for job execution logs

### Common Issues & Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Chatbot stuck processing | Redis key `processing:{phone}` not cleared | Ensure `finally` block in `process_webhook_message()` executes |
| Search endpoints return 500 | Embeddings not normalized before pgvector cast | Call `normalize_embeddings()` before SQL |
| Azure deploy fails | Docker/auth missing or Bicep misconfiguration | Run `azd pipeline config`, check `infra/main.parameters.json` alignment |
| LLM authentication errors | OpenAI vs Azure mode mismatch | Verify `USE_AZURE_OPENAI` flag matches your API keys |
| Redis connection fails | TLS required but `REDIS_USE_TLS=false` | Set `REDIS_USE_TLS=true` for Azure Cache |
| Admin dashboard empty | Cache stale or invalidation not called | Trigger `invalidate_dashboard_caches()` or clear Redis manually |

## Non-obvious Gotchas

- **Message/prompt updates require a restart**: `messages.yml` and `prompts.yml` are loaded via singletons at boot. Changes to these files only take effect after restarting the app.
- **No database migration tool**: The project has no Alembic setup. For dev use `reset_database.py`; for production plan manual SQL migrations.
- **`services/location` respects `USE_AZURE_OPENAI`**: The location client is initialized at module load alongside the other services; it uses `AzureOpenAI` when `USE_AZURE_OPENAI=True` and the Azure deployment name from `AZURE_DEPLOYMENT_NAME`.
- **URL shortener storage is shared**: The `/r/{short_id}` redirect route in `main.py` and `services/search.py` share the same Redis key format. Changing one requires updating the other.
- **`processing:{phone}` Redis key**: The chatbot sets this key to prevent concurrent handling. If a request crashes before the `finally` block in `process_webhook_message()`, the key stays set and the bot appears stuck.

