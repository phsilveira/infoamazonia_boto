# InfoAmazonia Boto Documentation Hub

This folder centralizes the living documentation for the Boto project. Every file here targets a specific audience:

| Doc | Purpose |
| --- | --- |
| `README.md` *(this file)* | High-level overview, architecture snapshot, and navigation map. |
| `MAINTAINERS.md` | Day-to-day operational guidance (infra, secrets, chatbot copy & prompts, debugging). |
| `next-steps.md` | Azure Developer CLI (azd) onboarding sequence after running `azd init`. |
| `API_DOCUMENTATION.md` | Swagger-aligned reference for the `/api/*` endpoints that power search & analytics. |
| `replit.md` | Deep dive into the FastAPI/WhatsApp architecture for folks working in hosted IDEs (Replit, Codespaces, etc.). |

If you add a new document, update this table so contributors know where to look.

## Architecture snapshot

The system is a FastAPI app deployed on Azure App Service, backed by Azure Database for PostgreSQL (with `pgvector`) and Azure Cache for Redis. Key flows:

1. **HTTP lifecycle** – `main.py` wires routers (`admin`, `webhook`, `routers.location`, `api_endpoints`), mounts static assets, and starts APScheduler.
2. **Admin portal** – Everything under `admin/` is split into focused routers (`users`, `news_sources`, `messages`, `interactions`, `articles`, `admin_users`, `metrics`, `scheduler`). Shared helpers live in `admin/base.py`.
3. **Chatbot** – Meta webhook traffic hits `webhook.py`, flows through `services.chatbot.ChatBot`, and delegates to state-specific handlers (`services/handlers.py`). Outbound replies go through `services/whatsapp.send_message`.
4. **Domain services** – Business logic resides in `services/` (chatgpt, embeddings, search, ingestion, email, location, etc.). Caching helpers live in `cache_utils.py`.
5. **Background jobs** – `scheduler.py` registers ingestion, digest, and cleanup tasks; when the app boots, `start_scheduler()` spins them up with the São Paulo timezone.

For additional operational guidance, jump to [`MAINTAINERS.md`](MAINTAINERS.md).

## Documentation map

- **Local & cloud workflows** → [`next-steps.md`](next-steps.md)
- **API details** → [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md)
- **Hosted IDE / Replit setup** → [`replit.md`](replit.md)
- **Admin UX & content updates** → sections below + `MAINTAINERS.md`

## Admin module overview

The original monolithic `admin.py` was decomposed into focused modules that mirror the UI tabs. Everything sits under `admin/`, and routers are automatically registered via `admin/__init__.py`.

### Core files

- `__init__.py` – Router composition and dependency wiring.
- `base.py` – Shared dependencies, cache invalidation helpers, template context utilities.

### Feature modules

- `users.py` – CRUD for subscribers, locations, subjects, and status.
- `news_sources.py` – Manage sources, trigger ingestion/downloads.
- `messages.py` – Preview WhatsApp copy, inspect scheduler runs, edit canned responses.
- `interactions.py` – Analytics exports, CTR data visualization.
- `articles.py` – Search/filter/export articles (vector + text).
- `admin_users.py` – Access control for staff accounts.
- `metrics.py` – Dashboard cards and trend charts.
- `scheduler.py` – Job definitions, run history, and manual triggers.

### Why the split matters

1. **Maintainability** – Each router handles one surface area and can evolve independently.
2. **Testing** – Modules can be exercised in isolation using FastAPI’s dependency override hooks.
3. **Scalability** – New admin features are side-loaded without touching unrelated code.
4. **Code reuse** – Shared logic lives in `base.py` and `cache_utils.py` instead of copy/paste.
5. **Team velocity** – Multiple contributors can work without stepping on each other.
6. **Debugging** – Production issues are easier to trace to a single module/router.

### Migration note

`admin_original_backup.py` remains in the repo for reference. The modular routers are backward compatible with the legacy templates and URLs, so no client-side changes were required.