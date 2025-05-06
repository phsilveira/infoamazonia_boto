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
        logger.debug(f"Article object created successfully for {news_item.get('_id')}")
        return article
    except Exception as e:
        logger.error(f"Error processing article {news_item.get('_id')}: {e}", exc_info=True)
        raise

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def process_scraped_article(url: str, source_name: str, language: str = "pt"):
    """Process article directly from a URL using web scraping"""
    try:
        from models import Article
        from services.embeddings import generate_embedding, generate_term_summary
        
        logger.debug(f"Processing article from URL: {url}")
        
        # Scrape the content from the URL
        content = get_website_text_content(url)
        if not content:
            logger.error(f"Failed to extract content from {url}")
            return None
            
        # Extract metadata
        metadata = extract_article_metadata(url)
        
        # Use metadata or fallbacks
        title = metadata.get('title', f"Article from {source_name}")
        published_date = metadata.get('published_date')
        author = metadata.get('author', 'Unknown')
        
        # Generate a unique ID
        article_id = str(uuid.uuid4())
        
        # Generate article summary
        logger.debug("Generating article summary")
        summary = generate_term_summary(title, content)
        logger.debug("Successfully generated summary")

        # Generate embedding for article content and metadata
        embedding_text = f"{title} {summary}"

        logger.debug(f"Generating embedding for text length: {len(embedding_text)}")
        embedding = generate_embedding(str(embedding_text))
        logger.debug("Successfully generated embedding")

        # Create the article object
        article = Article(
            id=article_id,
            title=title,
            content=content,
            summary_content=summary,
            original_id=article_id,
            collection_date=datetime.now(pytz.UTC),
            url=url,
            author=author,
            published_date=published_date if published_date else datetime.now(pytz.UTC),
            description=summary[:200] + "..." if len(summary) > 200 else summary,
            news_source=source_name,
            language=language,
            topics=[],
            subtopics=[],
            keywords=[],
            article_metadata={
                'scraped': True,
                'site': source_name,
            },
            embedding=embedding
        )
        
        logger.debug(f"Article object created successfully for {url}")
        return article
    except Exception as e:
        logger.error(f"Error processing article from URL {url}: {e}", exc_info=True)
        raise

def ingest_articles(news_items: List[Dict[str, Any]]) -> int:
    """Ingest multiple articles into the database with proper error handling"""
    # Import at function scope to allow dependency injection via sys.modules
    import sys
    
    # Get db from app module (injected by admin.py)
    if 'app' not in sys.modules:
        logger.error("app module not found. Make sure it's injected before calling this function.")
        return 0
        
    from app import db
    from models import Article
    
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

def ingest_scraped_articles_from_source(source_url: str, source_name: str, language: str = "pt") -> int:
    """
    Ingest articles directly from a news source URL using web scraping
    
    Args:
        source_url: The base URL of the news source
        source_name: Name of the news source for attribution
        language: Language code (default: "pt" for Portuguese)
        
    Returns:
        Number of articles successfully added
    """
    import sys
    import re
    import requests
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin, urlparse
    
    # Get db from app module (injected by admin.py)
    if 'app' not in sys.modules:
        logger.error("app module not found. Make sure it's injected before calling this function.")
        return 0
        
    from app import db
    from models import Article
    
    # Verify database connection
    try:
        # Use SQLAlchemy text() for raw SQL
        db.session.execute(text('SELECT 1'))
        logger.info("Database connection verified")
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise
    
    articles_added = 0
    errors = []
    
    logger.info(f"Starting scraping from news source: {source_name} ({source_url})")
    
    try:
        # Get the base domain for URL validation
        parsed_source = urlparse(source_url)
        base_domain = parsed_source.netloc
        
        # Fetch the main page
        response = requests.get(source_url, timeout=30)
        if response.status_code != 200:
            logger.error(f"Failed to fetch source URL: {source_url}, status code: {response.status_code}")
            return 0
            
        # Parse the HTML to find article links
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all('a', href=True)
        
        # Extract article URLs
        article_urls = []
        
        for link in links:
            href = link['href']
            
            # Make relative URLs absolute
            full_url = urljoin(source_url, href)
            parsed_url = urlparse(full_url)
            
            # Only include URLs from the same domain
            if parsed_url.netloc == base_domain:
                # Typical article URL patterns (customize based on site)
                article_patterns = [
                    r'/noticia/', r'/news/', r'/article/', r'/story/',
                    r'/\d{4}/\d{2}/', r'/post/', r'/reportagem/', r'/materia/'
                ]
                
                if any(re.search(pattern, parsed_url.path) for pattern in article_patterns):
                    if full_url not in article_urls:
                        article_urls.append(full_url)
        
        logger.info(f"Found {len(article_urls)} potential article URLs")
        
        # Process each article URL
        for i, url in enumerate(article_urls[:10]):  # Limit to 10 articles per source
            try:
                logger.debug(f"Processing article {i+1}/{min(10, len(article_urls))}: {url}")
                
                # Check if article already exists in database
                existing = Article.query.filter(Article.url == url).first()
                
                if existing:
                    logger.debug(f"Article with URL {url} already exists, skipping")
                    continue
                
                # Process the article
                article = process_scraped_article(url, source_name, language)
                
                if article:
                    db.session.add(article)
                    
                    # Commit after each successful article to prevent losing all on error
                    try:
                        db.session.commit()
                        articles_added += 1
                        logger.info(f"Successfully saved scraped article: {url}")
                    except Exception as commit_error:
                        logger.error(f"Error committing scraped article {url}: {commit_error}")
                        db.session.rollback()
                else:
                    logger.warning(f"Failed to process article {url}")
            
            except Exception as e:
                errors.append(f"Error processing URL {url}: {str(e)}")
                db.session.rollback()
                logger.error(f"Error ingesting article: {e}", exc_info=True)
                continue
                
    except Exception as e:
        logger.error(f"Error during news source scraping: {e}", exc_info=True)
        return 0
        
    if errors:
        logger.error(f"Encountered {len(errors)} errors during scraping: {errors}")
        
    logger.info(f"Scraping complete. Added {articles_added} new articles from {source_name}")
    return articles_added