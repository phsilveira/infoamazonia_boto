# replit.md

## Overview

This is a FastAPI-based admin panel application for the InfoAmazonia chatbot (BOTO) system. The application manages WhatsApp bot interactions, user management, article content, and news sources for providing Amazon-related news to users in Portuguese. It includes comprehensive admin features, AI-powered article search, and scheduled messaging capabilities.

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

The application is configured for deployment on Google Cloud Run with:
- **Environment**: Production and development configurations via environment files
- **Database**: PostgreSQL connection with connection pooling
- **Static Files**: Served directly by FastAPI
- **Port Configuration**: Runs on port 8000 (internal) exposed as port 80 (external)
- **Auto-scaling**: Supported by Cloud Run infrastructure

Key deployment considerations:
- Database URL automatically set by Replit
- Environment variables for API keys and external service configuration
- Automatic database schema creation on startup
- Background scheduler initialization for automated tasks

## Changelog

Changelog:
- July 6, 2025: Enhanced URL shortening with Redis support
  - Added Redis-backed URL storage with 30-day expiration
  - Implemented both sync and async versions of shorten_url function
  - Added FastAPI route handler for URL redirects (/r/<short_id>)
  - Enhanced CTR tracking with Redis persistence
  - Maintained fallback to in-memory cache for reliability
- June 17, 2025. Initial setup

## User Preferences

Preferred communication style: Simple, everyday language.