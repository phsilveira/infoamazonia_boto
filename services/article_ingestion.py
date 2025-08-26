import logging
from datetime import datetime
import pytz
import uuid
from typing import Dict, Any, List, Optional
import json
from tenacity import retry, stop_after_attempt, wait_exponential
from sqlalchemy import text

# Import web scraper
from services.web_scraper import get_website_text_content, extract_article_metadata

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def process_article(news_item: Dict[str, Any]):
    """Process a news item and create an Article object with retry logic"""
    try:
        from models import Article
        from services.embeddings import generate_embedding, generate_term_summary
        
        logger.debug(f"Processing article: {news_item.get('_id')}")

        # Process title based on news source
        title = news_item['Title']
        if news_item.get('news_source') == 'Amazon Underworld':
            # Remove "- Amazon Underworld" pattern from title
            title = title.replace(' - Amazon Underworld', '').replace('- Amazon Underworld', '')
            logger.debug(f"Processed title for Amazon Underworld: {title}")

        # Generate article summary
        logger.debug("Generating article summary")
        summary = generate_term_summary(title, news_item['content'])
        logger.debug("Successfully generated summary")

        # Generate embedding for article content and metadata
        embedding_text = f"{title} {' '.join(news_item.get('Keywords', []))} {summary}"

        logger.debug(f"Generating embedding for text length: {len(embedding_text)}")
        embedding = generate_embedding(str(embedding_text))
        logger.debug("Successfully generated embedding")

        article = Article(
            title=title,
            content=news_item['content'],
            summary_content=summary,  # Add the generated summary
            original_id=news_item['_id'],
            collection_date=news_item['collection_date'],
            url=news_item['URL'],
            author=news_item['Author'],
            published_date=datetime.fromisoformat(news_item['Published_date']) if news_item.get('Published_date') else None,
            description=news_item['Description'],
            news_source=news_item['news_source'],
            language=news_item['Language'],
            topics=news_item.get('News_topics', []),
            subtopics=news_item.get('Subtopics', []),
            keywords=news_item.get('Keywords', []),
            article_metadata={
                'location': news_item.get('location', {}),
                'site': news_item.get('site'),
            },
            embedding=embedding
        )
        logger.debug(f"Article object created successfully for {news_item.get('_id')}")
        return article
    except Exception as e:
        logger.error(f"Error processing article {news_item.get('_id')}: {e}", exc_info=True)
        raise

def ingest_articles(news_items: List[Dict[str, Any]]) -> int:
    """Ingest multiple articles into the database with proper error handling"""
    articles_added, _ = ingest_articles_with_ids(news_items)
    return articles_added

def ingest_articles_with_ids(news_items: List[Dict[str, Any]]) -> tuple[int, List[int]]:
    """Ingest multiple articles into the database and return count and IDs of newly added articles"""
    # Import at function scope to allow dependency injection via sys.modules
    import sys
    
    # Get db from app module (injected by admin.py)
    if 'app' not in sys.modules:
        logger.error("app module not found. Make sure it's injected before calling this function.")
        return 0, []
        
    from app import db
    from models import Article
    
    articles_added = 0
    newly_added_article_ids = []
    errors = []

    logger.info(f"Starting ingestion of {len(news_items)} articles")

    # Verify database connection
    try:
        # Use SQLAlchemy text() for raw SQL
        db.session.execute(text('SELECT 1'))
        logger.info("Database connection verified")
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

    for news_item in news_items:
        try:
            logger.debug(f"Processing article {articles_added + 1} of {len(news_items)}")

            # Check for duplicate - using Article.query which should be patched by caller
            existing = Article.query.filter(
                (Article.original_id == news_item['_id']) |
                (Article.url == news_item['URL'])
            ).first()

            if not existing:
                logger.debug(f"Article {news_item.get('_id')} is new, processing...")
                article = process_article(news_item)
                db.session.add(article)
                articles_added += 1
                # Commit after each successful article to prevent losing all on error
                try:
                    db.session.commit()
                    # Refresh to get the ID
                    db.session.refresh(article)
                    newly_added_article_ids.append(article.id)
                    logger.info(f"Successfully saved article {news_item.get('_id')} with ID {article.id}")
                except Exception as commit_error:
                    logger.error(f"Error committing article {news_item.get('_id')}: {commit_error}")
                    db.session.rollback()
                    raise
            else:
                logger.debug(f"Article {news_item.get('_id')} already exists, skipping")

        except Exception as e:
            errors.append(f"Error processing article {news_item.get('_id')}: {str(e)}")
            db.session.rollback()
            logger.error(f"Error ingesting article: {e}", exc_info=True)
            continue

    if errors:
        logger.error(f"Encountered {len(errors)} errors during ingestion: {errors}")

    logger.info(f"Ingestion complete. Added {articles_added} new articles with IDs: {newly_added_article_ids}")
    return articles_added, newly_added_article_ids