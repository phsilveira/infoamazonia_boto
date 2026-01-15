# replit.md

## Overview

> For the full documentation map, start with [docs/README.md](README.md). Stay here when you specifically need hosted-IDE instructions.

This guide is tailored for contributors working from hosted IDEs such as Replit, Codespaces, or GitHub.dev. It mirrors the core docs but highlights the workflows that matter when you are editing inside a browser. The FastAPI application powers the InfoAmazonia chatbot (BOTO) and handles WhatsApp interactions, admin tooling, article management, AI-assisted search, and scheduled messaging in Portuguese.

## System Architecture

The application follows a modular FastAPI architecture with the following key components:

- **Backend Framework**: FastAPI with Uvicorn server
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Authentication**: JWT-based session authentication with bcrypt password hashing
- **Caching**: Redis for performance optimization
- **AI Integration**: OpenAI/Azure OpenAI for embeddings and content generation
- **Task Scheduling**: APScheduler for automated messaging
- **Template Engine**: Jinja2 for HTML templates
- **External APIs**: WhatsApp API integration for bot messaging

## Key Components

### 1. Admin Dashboard
- User management (create, update, delete users)
- Admin user management with role-based access
- Article content management with AI-powered search
- News source management and article ingestion
- Interaction analytics and CTR statistics
- Message history and scheduler task monitoring

### 2. WhatsApp Bot Integration
- Webhook handler for WhatsApp messages
- State machine-based conversation flow
- AI-powered article summaries and term explanations
- Location-based news filtering
- Scheduled news delivery (daily, weekly, monthly)

### 3. AI Services
- OpenAI/Azure OpenAI integration for embeddings and completions
- Semantic article search using vector embeddings
- Automated content summarization
- Term explanation generation

### 4. Database Models
- Users with preferences and interaction history
- Articles with embeddings for semantic search
- News sources and content ingestion tracking
- Admin users with role-based permissions
- Message logs and scheduler run history

## Data Flow

1. **Article Ingestion**: News sources are scraped and processed into articles with AI-generated summaries and embeddings
2. **User Interaction**: WhatsApp messages trigger webhook handlers that process user requests through state machine
3. **AI Processing**: User queries are processed using OpenAI for article search, summarization, or term explanation
4. **Response Generation**: Responses are formatted and sent back via WhatsApp API
5. **Scheduling**: Background tasks send scheduled news updates to subscribed users
6. **Analytics**: All interactions are logged for admin monitoring and CTR analysis

## External Dependencies

- **OpenAI/Azure OpenAI**: For embeddings, completions, and content generation
- **WhatsApp Business API**: For bot messaging (both official and unofficial APIs supported)
- **PostgreSQL**: Primary database with pgvector extension for embedding search
- **Redis**: Caching layer for performance optimization
- **Google Maps API**: For location-based services
- **Mailgun**: Email services for admin notifications

## Deployment Strategy

We deploy to **Azure App Service** via Azure Developer CLI (`azd`). Container images are built from the root `Dockerfile` and published automatically when you run `azd deploy` (or via CI). Supporting services (Azure Database for PostgreSQL with `pgvector`, Azure Cache for Redis) are described in `infra/main.bicep` and provisioned through `azd up`.

- **Environment management** – Use `.env` + Replit secrets for local edits. When you need to sync values to Azure, run `python scripts/sync_env_to_azd.py --env dev` or `azd env set KEY VALUE`.
- **Database** – Managed PostgreSQL Flexible Server; Bicep injects `DATABASE_URL`, `PG*`, and Redis settings as app settings so App Service can reach them securely.
- **Static files & runtime** – FastAPI serves assets directly. App Service listens on port `8000` (`WEBSITES_PORT`), and the default startup command is `python -m uvicorn main:app --host 0.0.0.0 --port 8000` unless you override `STARTUP_COMMAND`.
- **Scaling** – Default SKU is `B1`. Upgrade to General Purpose tiers when you need pgvector or more CPU. APScheduler jobs run inside the web process, so keep them idempotent before enabling multiple instances.

When working from Replit/codespaces:
1. Start Postgres + Redis locally (Docker Compose works well) and set `DATABASE_URL`, `REDIS_*`, and API keys via the IDE’s secrets UI.
2. Install dependencies with `pip install -e .` then run `uvicorn main:app --reload --host 0.0.0.0 --port 8000`.
3. Before deploying, ensure the `vector` extension is allowed on the managed Postgres tier (General Purpose+) and that Redis TLS settings (`REDIS_USE_TLS`) match the target environment.

Key deployment considerations:
- Schema creation + `CREATE EXTENSION IF NOT EXISTS vector` happen during startup; the App Service logs will show failures if the database tier is incompatible.
- Background scheduler starts automatically. If you need to pause jobs (e.g., during maintenance), disable `start_scheduler()` via an environment flag or stop the site.
- Use `az webapp log tail` for live diagnostics and `azd monitor` (or Azure Portal → Log Stream) when debugging remote issues.

## Changelog

Recent changes:
- October 2, 2025: Enhanced admin users page with last message display
  - ✓ Added "Última Mensagem" (Last Message) column to admin users list
  - ✓ Implemented SQL join to fetch most recent incoming message for each user
  - ✓ Messages display truncated with full text on hover for better UX
  - ✓ Shows "-" placeholder when no incoming messages exist for a user
  - ✓ Query optimized with subquery and left join for performance
- August 27, 2025: Added URL detection and processing functionality
  - ✓ Created URL detection utility (utils/url_detector.py) supporting both protocol and non-protocol URLs
  - ✓ Added new 'process_url_state' to chatbot state machine with transitions from any state
  - ✓ Modified webhook.py process_message function to detect URLs in incoming messages
  - ✓ Created handle_url_processing_state handler that responds with "hello world" for testing
  - ✓ Updated ChatBot class with process_url() trigger method
  - ✓ Successfully tested URL detection with both https://example.com and www.google.com formats
  - ✓ Fixed state machine transition issues by using manual state setting instead of end_conversation
  - ✓ Modified URL detection to use handle_article_summary_state instead of handle_url_processing_state
  - ✓ URLs now trigger article summary functionality for content processing
- July 29, 2025: Fixed URL redirect authentication and Redis coroutine issues
  - ✓ Removed authentication requirement for `/r/{short_id}` redirect endpoints
  - ✓ Fixed RuntimeWarnings about unawaited coroutines in sync Redis operations
  - ✓ Updated middleware to exclude redirect paths from authentication
  - ✓ Verified redirect functionality works without login requirements
  - ✓ Maintained security for admin endpoints while allowing public URL redirects
- July 29, 2025: Refactored URL shortening functions with DRY principle
  - ✓ Eliminated code duplication between shorten_url and shorten_url_async functions
  - ✓ Created shared helper functions for Redis storage operations
  - ✓ Fixed Redis storage bug where impressions were incorrectly incrementing instead of initializing
  - ✓ Improved Redis error handling and fallback mechanisms
  - ✓ Verified URL shortening and redirect functionality working correctly
  - ✓ Enhanced code maintainability by separating sync and async Redis operations
- July 6, 2025: Refactored scheduler.py to use direct service calls
  - Modified send_news_template function to use list_articles_service directly instead of HTTP requests
  - Replaced HTTP ingestion API calls with direct download_news_from_sources function calls
  - Improved performance and reliability by eliminating all internal HTTP calls in scheduler
  - Fixed Redis async operation warnings by using shorten_url_async in list_articles_service
  - Enhanced error handling and reduced network overhead in scheduled tasks
  - Complete process now: ingests news from sources → fetches articles → sends to users
- July 6, 2025: Optimized WhatsApp handler service calls
  - Modified handle_term_info_state to use search_term_service directly instead of HTTP requests
  - Modified handle_article_summary_state to use search_articles_service directly instead of HTTP requests
  - Improved performance and reliability by eliminating internal HTTP calls
  - Maintained all existing functionality including error handling and user interactions
- July 6, 2025: Enhanced URL shortening with Redis support
  - Added Redis-backed URL storage with 30-day expiration
  - Implemented both sync and async versions of shorten_url function
  - Added FastAPI route handler for URL redirects (/r/<short_id>)
  - Enhanced CTR tracking with Redis persistence
  - Maintained fallback to in-memory cache for reliability
- June 17, 2025. Initial setup

## User Preferences

Preferred communication style: Simple, everyday language.