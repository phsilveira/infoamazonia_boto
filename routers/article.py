from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from models import Article
from app import db
from sqlalchemy import or_
from datetime import datetime

from search import shorten_url

article_bp = Blueprint('articles', __name__)

@article_bp.route('/articles/delete/<uuid:article_id>', methods=['POST'])
def delete_article(article_id):
    """Delete an article by its ID"""
    article = Article.query.get_or_404(article_id)

    try:
        db.session.delete(article)
        db.session.commit()
        if request.headers.get('Accept') == 'application/json':
            return jsonify({'success': True, 'message': 'Article deleted successfully'})
        else:
            flash('Article deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        if request.headers.get('Accept') == 'application/json':
            return jsonify({'success': False, 'message': str(e)}), 500
        else:
            flash(f'Error deleting article: {str(e)}', 'danger')

    return redirect(url_for('articles.list_articles'))

@article_bp.route('/articles')
def list_articles():
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of items per page
    search_query = request.args.get('search', '').strip()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    summary_query = request.args.get('summary', '').strip()

    # Base query
    query = Article.query

    # Apply search filter if search_query exists
    if search_query:
        search_filter = f"%{search_query}%"
        query = query.filter(Article.title.ilike(search_filter))

    # Apply date filters if they exist
    if date_from:
        try:
            date_from = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Article.published_date >= date_from)
        except ValueError:
            pass

    if date_to:
        try:
            date_to = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(Article.published_date <= date_to)
        except ValueError:
            pass

    # Apply summary content filter if it exists
    if summary_query:
        summary_filter = f"%{summary_query}%"
        query = query.filter(Article.summary_content.ilike(summary_filter))

    # Order by published_date and paginate
    pagination = query.order_by(Article.published_date.desc()).paginate(
        page=page, 
        per_page=per_page,
        error_out=False
    )

    # For API endpoint
    def get_articles_list(pagination_obj):
        return [{
            'id': str(article.id),
            'title': article.title,
            'url': shorten_url(article.url),
            'published_date': article.published_date.strftime('%Y-%m-%d') if article.published_date else None,
            'author': article.author,
            'description': article.description,
            'summary_content': article.summary_content,
            'news_source': article.news_source,
            'language': article.language,
            'news_source': article.news_source
        } for article in pagination_obj.items]

    # If it's an API request, return JSON
    if request.headers.get('Accept') == 'application/json':
        return jsonify({
            'success': True,
            'articles': get_articles_list(pagination),
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': pagination.page
        })

    return render_template(
        'articles/list.html',
        articles=pagination.items,
        pagination=pagination,
        search_query=search_query,
        date_from=date_from,
        date_to=date_to,
        summary_query=summary_query
    )