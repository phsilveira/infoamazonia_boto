from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from fastapi import Request, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text, func, select, or_
import models
from database import SessionLocal
import logging
import unicodedata
from cachetools import TTLCache, keys
from functools import wraps
import uuid
import urllib.parse
from typing import Dict, Any, List, Optional
from datetime import datetime
from services.embeddings import generate_embedding, generate_completion, generate_article_summary
from config import settings


# Import for compatibility with existing Flask routes
try:
    db = SessionLocal()
except ImportError:
    db = None

# Cache for search results (100 items, expire after 5 minutes)
search_cache = TTLCache(maxsize=100, ttl=300)

# URL shortening cache (maps short IDs to original URLs)
url_cache = TTLCache(maxsize=500, ttl=86400 * 30)  # 30 days cache

# Cache for tracking metrics (impressions and clicks)
url_impressions_cache = TTLCache(maxsize=1000, ttl=86400 * 30)  # 30 days cache
url_clicks_cache = TTLCache(maxsize=1000, ttl=86400 * 30)  # 30 days cache

def shorten_url(original_url, host_url=None, redis_client=None):
    """
    Creates a shortened URL for the original URL.
    Returns a tuple containing the path component and full URL.
    Also initializes tracking metrics for the URL.
    Uses Redis for persistent storage with 30-day expiration.
    """
    # Generate a short unique ID
    short_id = str(uuid.uuid4())[:8]

    # Store the original URL in Redis with 30-day expiration
    if redis_client:
        try:
            # Check if this is an async Redis client (redis.asyncio)
            import inspect
            is_async = inspect.iscoroutinefunction(redis_client.setex) if hasattr(redis_client, 'setex') else False
            
            if is_async:
                # This would need to be called in an async context
                # For now, fall back to in-memory cache if we can't use sync Redis
                raise Exception("Async Redis client not supported in sync context")
            else:
                # Store original URL
                redis_client.setex(f"url:{short_id}", 86400 * 30, original_url)
                
                # Initialize or increment impressions
                current_impressions = redis_client.get(f"impressions:{short_id}")
                if current_impressions is None:
                    redis_client.setex(f"impressions:{short_id}", 86400 * 30, "1")
                else:
                    redis_client.incr(f"impressions:{short_id}")
                    redis_client.expire(f"impressions:{short_id}", 86400 * 30)
                
                # Initialize clicks if not exists
                if not redis_client.exists(f"clicks:{short_id}"):
                    redis_client.setex(f"clicks:{short_id}", 86400 * 30, "0")
                
        except Exception as e:
            logging.error(f"Redis error in shorten_url: {e}. Falling back to in-memory cache.")
            # Fallback to in-memory cache if Redis fails
            url_cache[short_id] = original_url
            url_impressions_cache[short_id] = url_impressions_cache.get(short_id, 0) + 1
            if short_id not in url_clicks_cache:
                url_clicks_cache[short_id] = 0
    else:
        # Fallback to in-memory cache if Redis is not available
        url_cache[short_id] = original_url
        url_impressions_cache[short_id] = url_impressions_cache.get(short_id, 0) + 1
        if short_id not in url_clicks_cache:
            url_clicks_cache[short_id] = 0

    # Create short URL path
    short_path = f"/r/{short_id}"

    # For FastAPI compatibility, use provided host_url or fallback to path only
    if host_url:
        return host_url.rstrip('/') + short_path
    else:
        try:
            # Try to get Flask request context if available
            from flask import request
            return request.host_url.rstrip('/') + short_path
        except (RuntimeError, ImportError):
            # Fallback to just the path for FastAPI or when no request context
            return short_path

def cache_search_results(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Get request data
        data = request.get_json()
        # Create cache key from request data
        cache_key = keys.hashkey(
            func.__name__,
            data.get('query', ''),
            data.get('generate_summary', False),
            data.get('system_prompt', '')
        )

        # Try to get results from cache
        if cache_key in search_cache:
            return search_cache[cache_key]

        # If not in cache, execute function and cache results
        result = func(*args, **kwargs)
        search_cache[cache_key] = result
        return result
    return wrapper

search_bp = Blueprint('search', __name__)

@search_bp.route('/')
def index():
    return render_template('search.html')

@search_bp.route('/r/<short_id>')
def redirect_to_url(short_id):
    """
    Redirect to the original URL and track click metrics.
    """
    # Get Redis client from Flask app context
    redis_client = None
    try:
        from flask import current_app
        redis_client = getattr(current_app, 'redis', None)
    except:
        pass
    
    # Try to get original URL from Redis first
    original_url = None
    if redis_client:
        try:
            original_url = redis_client.get(f"url:{short_id}")
            # Increment click count
            redis_client.incr(f"clicks:{short_id}")
            redis_client.expire(f"clicks:{short_id}", 86400 * 30)  # Refresh expiration
        except Exception as e:
            logging.error(f"Redis error in redirect_to_url: {e}")
    
    # Fallback to in-memory cache
    if not original_url:
        original_url = url_cache.get(short_id)
        if original_url:
            url_clicks_cache[short_id] = url_clicks_cache.get(short_id, 0) + 1
    
    if original_url:
        return redirect(original_url)
    else:
        return "URL not found", 404

@search_bp.route('/search-articles')
def search_articles_page():
    return render_template('search_articles.html')

@search_bp.route('/ctr-stats')
def ctr_stats_page():
    """
    Page to display CTR statistics.
    """
    return render_template('ctr_stats.html')

@search_bp.route('/api/search-articles', methods=['POST'])
def search_articles():
    try:
        data = request.get_json()
        query = data.get('query')
        if not query:
            return jsonify({'error': 'Query is required'}), 400

        # Slugify the query
        normalized_query = unicodedata.normalize('NFKD', query).encode('ascii', 'ignore').decode('utf-8').lower()

        # Set similarity threshold
        similarity_threshold = 0.3  # Adjust this value for more or less strict matching

        # Use trigram similarity for title fuzzy matching and ILIKE for URL
        if db:  # Flask compatibility
            similar_articles = db.execute(
                select(models.Article, func.similarity(models.Article.title, normalized_query).label('similarity_score'))
                .filter(
                    (func.similarity(models.Article.title, normalized_query) > similarity_threshold) |
                    (models.Article.url.ilike(f'%{normalized_query}%'))  # Simple ILIKE for URL matching
                )
                .order_by(
                    func.greatest(
                        func.similarity(models.Article.title, normalized_query),
                        func.similarity(models.Article.url, normalized_query)
                    ).desc()
                )
                .limit(1)  # Limit the results to 2 articles
            ).all()
        else:
            similar_articles = []

        results = []
        
        # Get Redis client from Flask app context
        redis_client = None
        try:
            from flask import current_app
            redis_client = getattr(current_app, 'redis', None)
        except:
            pass
        
        for article, similarity_score in similar_articles:
            # Create shortened URL
            short_url = shorten_url(article.url, settings.HOST_URL, redis_client=redis_client)

            results.append({
                'id': str(article.id),
                'title': article.title,
                'url': article.url,
                'short_url': short_url,  # Add the shortened URL
                'published_date': article.published_date.strftime('%Y-%m-%-d') if article.published_date else None,
                'author': article.author,
                'description': article.description,
                'summary_content': generate_article_summary(
                    article.title, 
                    article.summary_content, 
                    short_url,
                    article.news_source,
                ),
                'key_words': article.keywords,
                'similarity': float(similarity_score)
            })

        return jsonify({
            'success': True,
            'results': results,
            'count': len(results)
        })

    except Exception as e:
        logging.error(f"Article search error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@search_bp.route('/api/search', methods=['POST'])
@cache_search_results
def search_term():
    try:
        data = request.get_json()
        query = data.get('query')
        if query:
            # Normalize the string to lowercase and remove special characters
            query = ''.join(e for e in query if e.isalnum() or e.isspace()).lower()
            query = remove_special_chars(query)
        if not query:
            return jsonify({'error': 'Query is required'}), 400

        # Generate embedding for query
        query_embedding = generate_embedding(query)

        query_embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'

        # Only use vector search if generate_embedding is available
        similar_articles = []
        if generate_embedding and db:
            # Perform vector similarity search using proper pgvector syntax
            semantic_sql_query = f"""
                SELECT id, title, content, url, published_date, author, description, keywords::text, article_metadata, summary_content, 
                       (1 - (embedding <=> '{query_embedding_str}'::vector))::float AS similarity
                FROM articles
                WHERE (1 - (embedding <=> '{query_embedding_str}'::vector))::float > 0.84
                ORDER BY similarity desc
                LIMIT 5
            """

            # Perform full text search
            fulltext_sql_query = f"""
                SELECT id, title, content, url, published_date, author, description, keywords::text, article_metadata, summary_content, 
                       ts_rank_cd(to_tsvector(title || ' ' || summary_content), plainto_tsquery('{query}')) AS similarity
                FROM articles
                WHERE to_tsvector(title || ' ' || summary_content) @@ plainto_tsquery('{query}')
                ORDER BY similarity desc
                LIMIT 5
            """

            # Combine results from semantic and full text search into a single query
            combined_sql_query = f"""
                ({semantic_sql_query})
                UNION
                ({fulltext_sql_query})
                ORDER BY similarity DESC
                LIMIT 10
            """

            # Execute the combined query and remove duplicates
            similar_articles = db.execute(text(combined_sql_query)).fetchall()
            similar_articles = list({v.id: v for v in similar_articles}.values())

        # Check if generation of summary is requested
        summary = None
        valid = None
        header = "📖 Aqui está o que descobrimos sobre o termo solicitado:\n\n"

        if data.get('generate_summary'):
            article_summaries = [
                f"Title: {article.title}\nContent: {article.summary_content}..." 
                for article in similar_articles[:10]
            ]
            summary = generate_completion(
                query,
                '\n\n'.join(article_summaries),
                system_prompt=data.get('system_prompt')
            )

        # Process the generated summary if available
        if summary:
            valid, summary = summary.split('|', 1)

        results = []
        
        # Get Redis client from Flask app context
        redis_client = None
        try:
            from flask import current_app
            redis_client = getattr(current_app, 'redis', None)
        except:
            pass
        
        for article in similar_articles:
            # Create shortened URL
            short_url = shorten_url(article.url, settings.HOST_URL, redis_client=redis_client)

            results.append({
                'id': str(article.id),
                'title': article.title,
                'similarity': float(article.similarity),
                'url': short_url,
                'short_url': short_url,  # Add the shortened URL
                'published_date': article.published_date.strftime('%Y-%m-%d') if article.published_date else None,
                'author': article.author,
                'description': article.description,
                'key_words': article.keywords
            })

        # Prepare WhatsApp summary response
        if valid == 'T':
            whatsapp_articles = "\n\n🔗 Fonte(s):" + ''.join(
                f"\n{article['title']}\n🔗 {article['short_url']}\n"
                for article in results[:5]
            )
            whatsapp_summary = header + summary + whatsapp_articles
        else:
            static_answer = """⚠️ Ops, não encontramos uma explicação completa para esse termo.

😕 Isso pode acontecer porque:
1️⃣ O termo é muito recente ou específico.
2️⃣ Não há consenso científico sobre o tema.
3️⃣ Não há informações detalhadas sobre o termo nas nossas fontes.

🔎 Nossa equipe irá investigar esse tema com mais profundidade. Obrigado por nos ajudar a entender o que nossa audiência tem interesse em consumir.
📌 Enquanto isso, você pode tentar reformular o termo ou buscar algo semelhante.
↩️ Voltando ao menu inicial...
"""
            whatsapp_summary = static_answer
            return jsonify({
                'success': False,
                'results': [],
                'count': len([]),
                'summary': whatsapp_summary
            })

        return jsonify({
            'success': True,
            'results': results,
            'count': len(results),
            'summary': whatsapp_summary
        })

    except Exception as e:
        logging.error(f"Search error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@search_bp.route('/api/article-stats')
def get_article_stats():
    try:
        # Get total count
        total_count = db.session.query(Article).count()

        # Get oldest and newest dates
        dates = db.session.query(
            db.func.min(Article.published_date).label('oldest'),
            db.func.max(Article.published_date).label('newest')
        ).first()

        return jsonify({
            'success': True,
            'stats': {
                'total_count': total_count,
                'oldest_date': dates.oldest.strftime('%Y-%m-%d') if dates.oldest else None,
                'newest_date': dates.newest.strftime('%Y-%m-%d') if dates.newest else None
            }
        })
    except Exception as e:
        logging.error(f"Error fetching article stats: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@search_bp.route('/api/ctr-stats')
def get_ctr_stats():
    """
    Get Click-Through Rate statistics for all shortened URLs.
    """
    try:
        # Get all short IDs from impressions cache (both Redis and in-memory)
        stats = []

        # Try to get Redis client from Flask app context
        redis_client = None
        try:
            from flask import current_app
            redis_client = getattr(current_app, 'redis', None)
        except:
            pass

        short_ids = set()
        
        # Get short IDs from Redis if available
        if redis_client:
            try:
                # Get all impression keys from Redis
                impression_keys = redis_client.keys("impressions:*")
                for key in impression_keys:
                    short_id = key.split(":")[-1]
                    short_ids.add(short_id)
            except Exception as e:
                logging.error(f"Error getting impression keys from Redis: {e}")

        # Also check in-memory cache for fallback
        short_ids.update(url_impressions_cache.keys())

        for short_id in short_ids:
            impressions = 0
            clicks = 0
            original_url = None

            # Try to get data from Redis first
            if redis_client:
                try:
                    impressions = int(redis_client.get(f"impressions:{short_id}") or 0)
                    clicks = int(redis_client.get(f"clicks:{short_id}") or 0)
                    original_url = redis_client.get(f"url:{short_id}")
                except Exception as e:
                    logging.error(f"Error getting data from Redis for {short_id}: {e}")

            # Fallback to in-memory cache if Redis failed or returned no data
            if impressions == 0 and clicks == 0 and original_url is None:
                impressions = url_impressions_cache.get(short_id, 0)
                clicks = url_clicks_cache.get(short_id, 0)
                original_url = url_cache.get(short_id)

            # Calculate CTR (avoid division by zero)
            ctr = (clicks / impressions * 100) if impressions > 0 else 0

            stats.append({
                'short_id': short_id,
                'short_url': f"/r/{short_id}",
                'original_url': original_url,
                'impressions': impressions,
                'clicks': clicks,
                'ctr': round(ctr, 2)  # Round to 2 decimal places
            })

        # Sort by CTR (highest first)
        stats.sort(key=lambda x: x['ctr'], reverse=True)

        # Calculate overall totals
        total_impressions = sum(item['impressions'] for item in stats)
        total_clicks = sum(item['clicks'] for item in stats)
        overall_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0

        return jsonify({
            'success': True,
            'stats': stats,
            'totals': {
                'total_urls': len(stats),
                'total_impressions': total_impressions,
                'total_clicks': total_clicks,
                'overall_ctr': round(overall_ctr, 2)
            }
        })
    except Exception as e:
        logging.error(f"Error fetching CTR stats: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

async def get_ctr_stats_service(redis_client=None, page=1, page_size=20):
    """
    FastAPI service function to get CTR statistics with pagination.
    Returns CTR stats for shortened URLs with pagination support.
    """
    try:
        # Get all unique short IDs from both Redis and in-memory cache
        short_ids = set()
        
        # Get short IDs from Redis
        if redis_client:
            try:
                # Get all URL keys from Redis
                url_keys = await redis_client.keys("url:*")
                for key in url_keys:
                    short_id = key.split(":")[-1]
                    short_ids.add(short_id)
            except Exception as e:
                logging.error(f"Error getting Redis keys: {e}")
        
        # Get short IDs from in-memory cache
        short_ids.update(url_cache.keys())
        
        stats = []
        
        for short_id in short_ids:
            impressions = 0
            clicks = 0
            original_url = None

            # Try to get data from Redis first
            if redis_client:
                try:
                    impressions_bytes = await redis_client.get(f"impressions:{short_id}")
                    clicks_bytes = await redis_client.get(f"clicks:{short_id}")
                    original_url = await redis_client.get(f"url:{short_id}")
                    
                    impressions = int(impressions_bytes) if impressions_bytes else 0
                    clicks = int(clicks_bytes) if clicks_bytes else 0
                except Exception as e:
                    logging.error(f"Error getting data from Redis for {short_id}: {e}")

            # Fallback to in-memory cache if Redis failed or returned no data
            if impressions == 0 and clicks == 0 and original_url is None:
                impressions = url_impressions_cache.get(short_id, 0)
                clicks = url_clicks_cache.get(short_id, 0)
                original_url = url_cache.get(short_id)

            # Calculate CTR (avoid division by zero)
            ctr = (clicks / impressions * 100) if impressions > 0 else 0

            stats.append({
                'short_id': short_id,
                'short_url': f"/r/{short_id}",
                'original_url': original_url,
                'impressions': impressions,
                'clicks': clicks,
                'ctr': round(ctr, 2)  # Round to 2 decimal places
            })

        # Sort by CTR (highest first)
        stats.sort(key=lambda x: x['ctr'], reverse=True)

        # Calculate overall totals (before pagination)
        total_items = len(stats)
        total_impressions = sum(item['impressions'] for item in stats)
        total_clicks = sum(item['clicks'] for item in stats)
        overall_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0

        # Apply pagination
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        paginated_stats = stats[start_index:end_index]

        # Calculate pagination info
        total_pages = (total_items + page_size - 1) // page_size  # Ceiling division
        has_next = page < total_pages
        has_prev = page > 1

        return {
            'success': True,
            'stats': paginated_stats,
            'totals': {
                'total_urls': total_items,
                'total_impressions': total_impressions,
                'total_clicks': total_clicks,
                'overall_ctr': round(overall_ctr, 2)
            },
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_items': total_items,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_prev': has_prev
            }
        }
    except Exception as e:
        logging.error(f"Error fetching CTR stats: {e}")
        return {
            'success': False,
            'error': str(e)
        }

async def shorten_url_async(original_url, host_url=None, redis_client=None):
    """
    Async version of shorten_url for use with async Redis clients.
    Creates a shortened URL for the original URL.
    Returns a tuple containing the path component and full URL.
    Also initializes tracking metrics for the URL.
    Uses Redis for persistent storage with 30-day expiration.
    """
    # Generate a short unique ID
    short_id = str(uuid.uuid4())[:8]

    # Store the original URL in Redis with 30-day expiration
    if redis_client:
        try:
            # Store original URL
            await redis_client.setex(f"url:{short_id}", 86400 * 30, original_url)
            
            # Initialize or increment impressions
            current_impressions = await redis_client.get(f"impressions:{short_id}")
            if current_impressions is None:
                await redis_client.setex(f"impressions:{short_id}", 86400 * 30, "1")
            else:
                await redis_client.incr(f"impressions:{short_id}")
                await redis_client.expire(f"impressions:{short_id}", 86400 * 30)
            
            # Initialize clicks if not exists
            if not await redis_client.exists(f"clicks:{short_id}"):
                await redis_client.setex(f"clicks:{short_id}", 86400 * 30, "0")
                
        except Exception as e:
            logging.error(f"Redis error in shorten_url_async: {e}. Falling back to in-memory cache.")
            # Fallback to in-memory cache if Redis fails
            url_cache[short_id] = original_url
            url_impressions_cache[short_id] = url_impressions_cache.get(short_id, 0) + 1
            if short_id not in url_clicks_cache:
                url_clicks_cache[short_id] = 0
    else:
        # Fallback to in-memory cache if Redis is not available
        url_cache[short_id] = original_url
        url_impressions_cache[short_id] = url_impressions_cache.get(short_id, 0) + 1
        if short_id not in url_clicks_cache:
            url_clicks_cache[short_id] = 0

    # Create short URL path
    short_path = f"/r/{short_id}"

    # For FastAPI compatibility, use provided host_url or fallback to path only
    if host_url:
        return host_url.rstrip('/') + short_path
    else:
        try:
            # Try to get Flask request context if available
            from flask import request
            return request.host_url.rstrip('/') + short_path
        except (RuntimeError, ImportError):
            # Fallback to just the path for FastAPI or when no request context
            return short_path

def remove_special_chars(text):
    """Normalize text for search by removing accents but keeping letters"""
    # Remove accents but keep all letters (including non-ASCII)
    normalized = unicodedata.normalize('NFD', text)
    without_accents = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    return without_accents.lower()

# FastAPI-compatible functions
async def get_article_stats_service(db: Session) -> Dict[str, Any]:
    """FastAPI-compatible version of get_article_stats"""
    try:
        # Get total count
        total_count = db.query(models.Article).count()

        # Get oldest and newest dates
        dates_query = db.query(
            func.min(models.Article.published_date).label('oldest'),
            func.max(models.Article.published_date).label('newest')
        ).first()

        oldest_date = None
        newest_date = None
        
        if dates_query and dates_query.oldest:
            oldest_date = dates_query.oldest.strftime('%d/%m/%Y')
        
        if dates_query and dates_query.newest:
            newest_date = dates_query.newest.strftime('%d/%m/%Y')
        
        logging.info(f"Article stats: {total_count} articles, oldest: {oldest_date}, newest: {newest_date}")
        
        return {
            "success": True,
            "stats": {
                "total_count": total_count,
                "oldest_date": oldest_date,
                "newest_date": newest_date
            }
        }
    except Exception as e:
        logging.error(f"Error fetching article stats: {e}")
        return {
            "success": False,
            "error": str(e)
        }

async def search_term_service(query: str, db: Session, generate_summary: bool = False, system_prompt: Optional[str] = None, redis_client=None) -> Dict[str, Any]:
    """FastAPI-compatible version of search_term function - EXACTLY equal to original"""
    try:
        if query:
            # Normalize the string to lowercase and remove special characters
            query = ''.join(e for e in query if e.isalnum() or e.isspace()).lower()
            query = remove_special_chars(query)
        if not query:
            return {'success': False, 'error': 'Query is required'}

        # Try to generate embedding for query
        query_embedding = None
        use_vector_search = False
        try:
            if callable(generate_embedding):
                query_embedding = generate_embedding(query)
                if query_embedding:
                    use_vector_search = True
        except Exception as e:
            logging.warning(f"Embedding generation failed: {e}")
            use_vector_search = False

        similar_articles = []
        
        if use_vector_search and query_embedding:
            # Perform vector similarity search using proper pgvector syntax
            query_embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
            semantic_sql_query = f"""
                SELECT id, title, content, url, published_date, author, description, keywords::text, article_metadata, summary_content, 
                       (1 - (embedding <=> '{query_embedding_str}'::vector))::float AS similarity
                FROM articles
                WHERE embedding IS NOT NULL
                and (1 - (embedding <=> '{query_embedding_str}'::vector))::float > 0.44
                ORDER BY similarity desc
            """
            
            # Perform full text search
            fulltext_sql_query = f"""
                SELECT id, title, content, url, published_date, author, description, keywords::text, article_metadata, summary_content, 
                       ts_rank_cd(
                    to_tsvector(
                      'portuguese',
                      coalesce(title,'') || ' ' || coalesce(summary_content,'')
                    ),
                    plainto_tsquery('portuguese','{query}')
                  ) AS similarity
                                FROM articles
                                WHERE to_tsvector(
                    'portuguese',
                    coalesce(title,'') || ' ' || coalesce(summary_content,'')
                  )
                  @@ plainto_tsquery('portuguese','{query}')
                    ORDER BY similarity desc
                """

            # Combine results from semantic and full text search into a single query
            combined_sql_query = f"""
                ({semantic_sql_query})
                UNION
                ({fulltext_sql_query})
                ORDER BY similarity DESC
            """
            
            # Execute the combined query and remove duplicates
            similar_articles = db.execute(text(combined_sql_query)).fetchall()
            similar_articles = list({v.id: v for v in similar_articles}.values())
        
        else:
            # Fall back to full text search only
            fulltext_sql_query = f"""
                SELECT id, title, content, url, published_date, author, description, keywords::text, article_metadata, summary_content, 
                       ts_rank_cd(
                    to_tsvector(
                      'portuguese',
                      coalesce(title,'') || ' ' || coalesce(summary_content,'')
                    ),
                    plainto_tsquery('portuguese','{query}')
                  ) AS similarity
                                FROM articles
                                WHERE to_tsvector(
                    'portuguese',
                    coalesce(title,'') || ' ' || coalesce(summary_content,'')
                  )
                  @@ plainto_tsquery('portuguese','{query}')
                    ORDER BY similarity desc
                """
            
            # Execute the full text search query
            similar_articles = db.execute(text(fulltext_sql_query)).fetchall()

        # Check if generation of summary is requested
        summary = None
        valid = None
        header = "📖 Aqui está o que descobrimos sobre o termo solicitado:\n\n"

        if generate_summary:
            article_summaries = [
                f"Title: {article.title}\nContent: {article.summary_content}..." 
                for article in similar_articles[:10]
            ]
            if generate_completion:
                summary = generate_completion(
                    query,
                    '\n\n'.join(article_summaries)
                )

        # Process the generated summary if available
        if summary:
            valid, summary = summary.split('|', 1)

        results = []
        for article in similar_articles:
            # Create shortened URL using Redis-backed URL shortening
            if redis_client:
                short_url = await shorten_url_async(article.url, settings.HOST_URL, redis_client=redis_client)
            else:
                short_url = shorten_url(article.url, settings.HOST_URL, redis_client=redis_client)

            # Parse keywords from PostgreSQL array format to Python list
            keywords = []
            if article.keywords:
                try:
                    # Remove the curly braces and split by comma
                    keywords_str = article.keywords.strip('{}')
                    if keywords_str:
                        # Split by comma and clean each keyword
                        keywords = [k.strip().strip('"') for k in keywords_str.split(',')]
                except Exception as e:
                    logging.warning(f"Failed to parse keywords '{article.keywords}': {e}")
                    keywords = []

            results.append({
                'id': str(article.id),
                'title': article.title,
                'similarity': float(article.similarity),
                'url': article.url,
                'short_url': short_url,  # Add the shortened URL
                'published_date': article.published_date.strftime('%Y-%m-%d') if article.published_date else None,
                'author': article.author,
                'description': article.description,
                'key_words': keywords
            })

        # Prepare WhatsApp summary response
        if generate_summary and valid == 'T':
            whatsapp_articles = "\n\n🔗 Fonte(s):" + ''.join(
                f"\n{article['title']}\n🔗 {article['short_url']}\n"
                for article in results[:3]
            )
            whatsapp_summary = header + summary + whatsapp_articles
        elif generate_summary and valid != 'T':
            static_answer = """⚠️ Ops, não encontramos uma explicação completa para esse termo.

😕 Isso pode acontecer porque:
1️⃣ O termo é muito recente ou específico.
2️⃣ Não há consenso científico sobre o tema.
3️⃣ Não há informações detalhadas sobre o termo nas nossas fontes.

🔎 Nossa equipe irá investigar esse tema com mais profundidade. Obrigado por nos ajudar a entender o que nossa audiência tem interesse em consumir.
📌 Enquanto isso, você pode tentar reformular o termo ou buscar algo semelhante.
↩️ Voltando ao menu inicial...
"""
            whatsapp_summary = static_answer
        else:
            # No summary generation requested, just return results
            whatsapp_summary = None

        return {
            'success': True,
            'results': results,
            'count': len(results),
            'summary': whatsapp_summary
        }

    except Exception as e:
        logging.error(f"Search error: {e}")
        return {
            'success': False,
            'error': str(e)
        }

async def search_articles_service(query: str, db: Session, redis_client=None) -> Dict[str, Any]:
    """FastAPI-compatible version of search_articles function"""
    try:
        if not query:
            return {'error': 'Query is required'}

        # Slugify the query
        normalized_query = unicodedata.normalize('NFKD', query).encode('ascii', 'ignore').decode('utf-8').lower()

        # Set similarity threshold
        similarity_threshold = 0.3  # Adjust this value for more or less strict matching

        similar_articles = db.execute(
            select(models.Article, func.similarity(models.Article.title, normalized_query).label('similarity_score'))
            .filter(
                (func.similarity(models.Article.title, normalized_query) > similarity_threshold) |
                (models.Article.url.ilike(f'%{normalized_query}%'))  # Simple ILIKE for URL matching
            )
            .order_by(
                func.greatest(
                    func.similarity(models.Article.title, normalized_query),
                    func.similarity(models.Article.url, normalized_query)
                ).desc()
            )
            .limit(1)  # Limit the results to 2 articles
        ).all()

        results = []
        
        for article, similarity_score in similar_articles:
            # Create shortened URL using Redis-backed URL shortening
            if redis_client:
                short_url = await shorten_url_async(article.url, settings.HOST_URL, redis_client=redis_client)
            else:
                short_url = shorten_url(article.url, settings.HOST_URL, redis_client=redis_client)

            # Parse keywords from PostgreSQL array format to Python list
            keywords = []
            if article.keywords:
                try:
                    # Remove the curly braces and split by comma
                    keywords_str = article.keywords.strip('{}')
                    if keywords_str:
                        # Split by comma and clean each keyword
                        keywords = [k.strip().strip('"') for k in keywords_str.split(',')]
                except Exception as e:
                    logging.warning(f"Failed to parse keywords '{article.keywords}': {e}")
                    keywords = []

            results.append({
                'id': str(article.id),
                'title': article.title,
                'url': short_url,
                'short_url': short_url,  # Add the shortened URL
                'published_date': article.published_date.strftime('%Y-%m-%d') if article.published_date else None,
                'author': article.author,
                'description': article.description,
                'summary_content': generate_article_summary(
                    article.title, 
                    article.summary_content, 
                    short_url,
                    article.news_source,
                ),
                'key_words': keywords,
                'similarity': float(similarity_score)
            })

        # Prepare response data
        response_data = {
            'success': True,
            'results': results,
            'count': len(results),
            'query': query
        }
        
        return response_data

    except Exception as e:
        logging.error(f"Article search error: {e}")
        return {
            'success': False,
            'error': str(e)
        }

@search_bp.route('/r/<short_id>')
def redirect_to_article(short_id):
    """
    Redirect to the original article URL with UTM parameters.
    Also tracks click for CTR calculation.
    """
    # Get the original URL from the cache
    original_url = url_cache.get(short_id)

    if not original_url:
        # Handle case when URL is not found (expired or invalid ID)
        return render_template('404.html', message="Link expired or not found"), 404

    # Track the click
    url_clicks_cache[short_id] = url_clicks_cache.get(short_id, 0) + 1

    # Parse the original URL
    parsed_url = urllib.parse.urlparse(original_url)

    # Get existing query parameters
    query_params = dict(urllib.parse.parse_qsl(parsed_url.query))

    # Add UTM parameters
    query_params.update({
        "utmSource": "whatsapp",
        "utmMedium": "news"
    })

    # Build the new query string
    new_query = urllib.parse.urlencode(query_params)

    # Construct the new URL with UTM parameters
    new_url = urllib.parse.urlunparse((
        parsed_url.scheme,
        parsed_url.netloc,
        parsed_url.path,
        parsed_url.params,
        new_query,
        parsed_url.fragment
    ))

    # Redirect to the new URL
    return redirect(new_url)


async def list_articles_service(
    db: Session,
    page: int = 1,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    summary: Optional[str] = None,
    redis_client=None
):
    """
    Service function to list articles with filtering and pagination.
    Returns a structured response for API consumption.
    """
    try:
        per_page = 10
        
        # Base query
        query = db.query(models.Article)
        
        # Apply search filter if search query exists
        if search:
            search_filter = f"%{search.strip()}%"
            query = query.filter(models.Article.title.ilike(search_filter))
        
        # Apply date filters if they exist
        if date_from:
            try:
                date_from_parsed = datetime.strptime(date_from, '%Y-%m-%d')
                query = query.filter(models.Article.published_date >= date_from_parsed)
            except ValueError:
                return {
                    "success": False,
                    "articles": [],
                    "total": 0,
                    "pages": 0,
                    "current_page": page,
                    "error": "Invalid date_from format. Use YYYY-MM-DD format."
                }
        
        if date_to:
            try:
                date_to_parsed = datetime.strptime(date_to, '%Y-%m-%d')
                query = query.filter(models.Article.published_date <= date_to_parsed)
            except ValueError:
                return {
                    "success": False,
                    "articles": [],
                    "total": 0,
                    "pages": 0,
                    "current_page": page,
                    "error": "Invalid date_to format. Use YYYY-MM-DD format."
                }
        
        # Apply summary content filter if it exists
        if summary:
            summary_filter = f"%{summary.strip()}%"
            query = query.filter(models.Article.summary_content.ilike(summary_filter))
        
        # Get total count before pagination
        total = query.count()
        
        # Calculate total pages
        pages = (total + per_page - 1) // per_page
        
        # Apply pagination and ordering
        articles = query.order_by(models.Article.published_date.desc()).offset((page - 1) * per_page).limit(per_page).all()
        
        # Format articles for response
        formatted_articles = []
        for article in articles:
            formatted_articles.append({
                "id": str(article.id),
                "title": article.title or "",
                "url": await shorten_url_async(article.url or "", settings.HOST_URL, redis_client=redis_client),
                "published_date": article.published_date.strftime('%Y-%m-%d') if article.published_date else None,
                "author": article.author,
                "description": article.description,
                "summary_content": article.summary_content,
                "news_source": article.news_source,
                "language": article.language
            })
        
        return {
            "success": True,
            "articles": formatted_articles,
            "total": total,
            "pages": pages,
            "current_page": page
        }
        
    except Exception as e:
        logging.error(f"Error in list_articles_service: {str(e)}")
        return {
            "success": False,
            "articles": [],
            "total": 0,
            "pages": 0,
            "current_page": page,
            "error": f"Internal server error: {str(e)}"
        }