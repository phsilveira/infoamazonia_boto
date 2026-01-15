# API Documentation - FastAPI Endpoints

> This reference sits alongside the other guides cataloged in [docs/README.md](README.md). Use it when you need precise request/response contracts for the `/api/*` routes.

## Overview
This document provides comprehensive Swagger/OpenAPI documentation for the API endpoints in `api_endpoints.py`. The API provides advanced search capabilities with AI-powered features for article management.

## Base URL
- Development: `http://localhost:8000`
- Production: `https://your-domain.com`

## Authentication
All endpoints require session-based authentication. Unauthenticated requests will be redirected to `/login`.

## API Endpoints

### 1. Get Article Statistics
**GET** `/api/article-stats`

**Summary:** Get Article Statistics  
**Description:** Retrieve comprehensive statistics about articles in the database including total count, oldest and newest publication dates  
**Tags:** Statistics

**Response Model:** `ArticleStatsResponse`

**Responses:**
- **200 OK** - Successfully retrieved article statistics
  ```json
  {
    "success": true,
    "stats": {
      "total_count": 1250,
      "oldest_date": "01/01/2020", 
      "newest_date": "10/06/2025"
    }
  }
  ```
- **302 Found** - Redirect to login (authentication required)
- **500 Internal Server Error** - Database connection failed
  ```json
  {
    "success": false,
    "error": "Database connection failed"
  }
  ```

---

### 2. Advanced Article Search
**POST** `/api/search`

**Summary:** Advanced Article Search  
**Description:** Perform intelligent article search using vector similarity and full-text search with optional AI-generated summaries  
**Tags:** Search

**Request Model:** `SearchQuery`
```json
{
  "query": "artificial intelligence",
  "generate_summary": true,
  "system_prompt": "Provide a brief technical summary"
}
```

**Response Model:** `SearchResponse`

**Responses:**
- **200 OK** - Search completed successfully
  ```json
  {
    "success": true,
    "results": [
      {
        "id": "123",
        "title": "Understanding Artificial Intelligence",
        "similarity": 0.95,
        "url": "https://example.com/article/123",
        "short_url": "/admin/articles/123",
        "published_date": "2024-06-10",
        "author": "Dr. Jane Smith",
        "description": "A comprehensive guide to AI concepts",
        "key_words": ["AI", "machine learning", "technology"]
      }
    ],
    "count": 1,
    "summary": "📖 Aqui está o que descobrimos sobre o termo solicitado..."
  }
  ```
- **302 Found** - Redirect to login (authentication required)
- **400 Bad Request** - Invalid search parameters
  ```json
  {
    "success": false,
    "error": "Query is required"
  }
  ```
- **500 Internal Server Error** - Search service unavailable

**Features:**
- **Vector Similarity Search**: Uses embeddings for semantic matching
- **Full-Text Search**: Traditional keyword-based search  
- **AI Summaries**: Optional AI-generated summaries of results
- **Custom Prompts**: Personalized summary generation

---

### 3. Search Articles by Query
**POST** `/api/search-articles`

**Summary:** Search Articles by Query  
**Description:** Search for specific articles using a text query with similarity matching  
**Tags:** Search

**Request Model:** `ArticleSearchQuery`
```json
{
  "query": "machine learning"
}
```

**Response Model:** `ArticleSearchResponse`

**Responses:**
- **200 OK** - Search completed successfully
  ```json
  {
    "success": true,
    "results": [
      {
        "id": "456",
        "title": "Machine Learning Applications",
        "similarity": 0.88,
        "url": "https://example.com/article/456", 
        "short_url": "/admin/articles/456",
        "published_date": "2024-06-09",
        "author": "Prof. John Doe",
        "description": "Exploring practical ML applications",
        "key_words": ["machine learning", "applications", "AI"]
      }
    ],
    "count": 1
  }
  ```
- **302 Found** - Redirect to login (authentication required)
- **400 Bad Request** - Missing or invalid query
- **500 Internal Server Error** - Search service unavailable

---

### 4. Search Articles Page
**GET** `/search-articles`

**Summary:** Search Articles Page  
**Description:** Render the search articles HTML page with article statistics  
**Tags:** Pages

**Response:** HTML page with search interface

**Responses:**
- **200 OK** - Successfully rendered search articles page
- **302 Found** - Redirect to login (authentication required)

---

## Data Models

### SearchQuery
```json
{
  "query": "string (required, min_length=1)",
  "generate_summary": "boolean (default: false)", 
  "system_prompt": "string (optional)"
}
```

### ArticleSearchQuery  
```json
{
  "query": "string (required, min_length=1)"
}
```

### SearchResult
```json
{
  "id": "string",
  "title": "string",
  "similarity": "float (0-1)",
  "url": "string", 
  "short_url": "string",
  "published_date": "string (YYYY-MM-DD, optional)",
  "author": "string (optional)",
  "description": "string (optional)",
  "key_words": "array of strings (optional)"
}
```

### ArticleStats
```json
{
  "total_count": "integer",
  "oldest_date": "string (DD/MM/YYYY, optional)",
  "newest_date": "string (DD/MM/YYYY, optional)"
}
```

### SearchResponse
```json
{
  "success": "boolean",
  "results": "array of SearchResult",
  "count": "integer",
  "summary": "string (optional)",
  "error": "string (optional)"
}
```

### ArticleStatsResponse
```json
{
  "success": "boolean", 
  "stats": "ArticleStats (optional)",
  "error": "string (optional)"
}
```

### ArticleSearchResponse
```json
{
  "success": "boolean",
  "results": "array of SearchResult", 
  "count": "integer",
  "error": "string (optional)"
}
```

## Example Usage

### Search with AI Summary
```bash
curl -X POST "http://localhost:8000/api/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "climate change",
    "generate_summary": true,
    "system_prompt": "Summarize environmental impact findings"
  }'
```

### Simple Article Search
```bash
curl -X POST "http://localhost:8000/api/search-articles" \
  -H "Content-Type: application/json" \
  -d '{"query": "renewable energy"}'
```

### Get Article Statistics
```bash
curl -X GET "http://localhost:8000/api/article-stats"
```

## Error Handling
All endpoints return consistent error responses with:
- `success`: boolean indicating operation status
- `error`: string describing the error when `success` is false
- Appropriate HTTP status codes (400, 500, etc.)

## Notes
- All endpoints require valid session authentication
- Search operations support both Portuguese and English queries
- AI summaries are generated in Portuguese by default
- Vector similarity search uses pgvector extension for semantic matching
- Results are cached using Redis for improved performance