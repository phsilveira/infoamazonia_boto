from flask import Blueprint, jsonify
from services.article_ingestion import ingest_articles
from services.news import News
import logging
from models import Article
from services.search import shorten_url  # Import Article model to access the newly added articles

ingestion_bp = Blueprint('ingestion', __name__)

@ingestion_bp.route('/api/ingest', methods=['POST'])
def ingest():
    try:
        # Initialize the News class
        news = News()

        # Fetch news from configured sources
        result = news.get_news()

        if not result['success']:
            return jsonify({
                'success': False,
                'error': 'Failed to fetch news from sources'
            }), 500

        # Process and store articles
        articles_added = ingest_articles(result['news'])

        return jsonify({
            'success': True,
            'articles_added': articles_added,
            'total_articles': result['number_of_news']
        })

    except Exception as e:
        logging.error(f"Ingestion error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@ingestion_bp.route('/api/download-articles', methods=['POST'])
def download_articles():
    try:
        news = News()
        result = news.get_news()

        if not result.get('success', False):
            return {
                'success': False,
                'articles': [],
                'total_articles': 0,
                'message': 'Failed to fetch articles from sources. Check logs for details.'
            }

        # Get the number of articles that were added
        articles_added_count = ingest_articles(result.get('news', []))

        # Query the most recent articles that were added
        # The ingest_articles function returns the count of articles added, not IDs
        # So we'll get the most recently added articles equal to that count
        if articles_added_count > 0:
            recent_articles = Article.query.order_by(Article.created_at.desc()).limit(articles_added_count).all()

            # Format the articles according to the API specification
            formatted_articles = [{
                'id': str(article.id),
                'title': article.title,
                'url': shorten_url(article.url),
                'published_date': article.published_date.strftime('%Y-%m-%d') if article.published_date else None,
                'author': article.author,
                'news_source': article.news_source,
                'language': article.language,
                'topics': article.topics,
                'description': article.description,
                'summary_content': article.summary_content,
                'news_source': article.news_source,
            } for article in recent_articles]

            return {
                'success': True,
                'articles': formatted_articles,
                'total_articles': articles_added_count,
                'message': f"Successfully downloaded and processed {articles_added_count} new articles"
            }
        else:
            # If no articles were added
            return {
                'success': True,
                'articles': [],
                'total_articles': 0,
                'message': "No new articles were found or all articles already exist in the database"
            }

    except Exception as e:
        logging.error(f"Article download error: {e}")
        return {
            'success': False,
            'articles': [],
            'total_articles': 0,
            'message': f"Error downloading articles: {str(e)}"
        }