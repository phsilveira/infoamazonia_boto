import logging
from datetime import datetime
import pytz
from typing import Dict, Any, List
import json
from tenacity import retry, stop_after_attempt, wait_exponential
from sqlalchemy import text
# Import locally within functions to allow for dependency injection
# from services.embeddings import generate_embedding, generate_term_summary

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def process_article(news_item: Dict[str, Any]) -> Article:
    """Process a news item and create an Article object with retry logic"""
    try:
        logger.debug(f"Processing article: {news_item.get('_id')}")

        # Generate article summary
        logger.debug("Generating article summary")
        summary = generate_term_summary(news_item['Title'], news_item['content'])
        logger.debug("Successfully generated summary")

        # Generate embedding for article content and metadata
        embedding_text = f"{news_item['Title']} {' '.join(news_item.get('Keywords', []))} {summary}"

        logger.debug(f"Generating embedding for text length: {len(embedding_text)}")
        embedding = generate_embedding(str(embedding_text))
        logger.debug("Successfully generated embedding")



        article = Article(
            title=news_item['Title'],
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
        # article['']
        logger.debug(f"Article object created successfully for {news_item.get('_id')}")
        return article
    except Exception as e:
        logger.error(f"Error processing article {news_item.get('_id')}: {e}", exc_info=True)
        raise

def ingest_articles(news_items: List[Dict[str, Any]]) -> int:
    """Ingest multiple articles into the database with proper error handling"""
    articles_added = 0
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

            # Check for duplicate
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
                    logger.info(f"Successfully saved article {news_item.get('_id')}")
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

    logger.info(f"Ingestion complete. Added {articles_added} new articles")
    return articles_added