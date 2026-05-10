#!/usr/bin/env python3
"""
Backfill partner source names and content for existing articles.

For each article ingested from InfoAmazonia that actually came from a partner outlet,
this script:
  1. Re-fetches the WP post to check the partner taxonomy
  2. Resolves the partner name
  3. Fetches full content via Firecrawl from the original partner URL
  4. Regenerates the article summary and embedding
  5. Updates news_source, content, summary_content, and embedding in the DB

Usage:
    python scripts/backfill_partner_articles.py [--dry-run] [--page-limit 50]
"""

import sys
import os
import argparse
import logging
import requests

# Allow imports from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

WP_API_BASE = "https://infoamazonia.org/wp-json/wp/v2"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}

# Cache partner ID → name to avoid redundant API calls
_partner_cache: dict[int, str] = {}


def fetch_partner_name(partner_id: int) -> str | None:
    if partner_id in _partner_cache:
        return _partner_cache[partner_id]
    try:
        resp = requests.get(f"{WP_API_BASE}/partner/{partner_id}", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        name = resp.json().get("name") or None
        if name:
            _partner_cache[partner_id] = name
        return name
    except Exception as e:
        logger.warning(f"Could not resolve partner {partner_id}: {e}")
        return None


def fetch_wp_posts_page(page: int, per_page: int = 10) -> list[dict]:
    try:
        resp = requests.get(
            f"{WP_API_BASE}/posts",
            params={"page": page, "per_page": per_page},
            headers=HEADERS,
            timeout=30,
        )
        if resp.status_code == 400:
            return []
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error fetching WP page {page}: {e}")
        return []


def scrape_with_firecrawl(url: str) -> str | None:
    from services.firecrawl import scrape_article
    return scrape_article(url)


def regenerate_summary_and_embedding(title: str, content: str):
    from services.embeddings import generate_embedding, generate_term_summary
    summary = generate_term_summary(title, content)
    embedding_text = f"{title} {summary}"
    embedding = generate_embedding(embedding_text)
    return summary, embedding


def main():
    parser = argparse.ArgumentParser(description="Backfill partner source names and content")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing to DB")
    parser.add_argument("--page-limit", type=int, default=10000, help="Max WP pages to scan (10 posts each, default: all)")
    args = parser.parse_args()

    db = SessionLocal()
    updated = 0
    skipped = 0
    not_found = 0
    firecrawl_failed = 0

    try:
        for page in range(1, args.page_limit + 1):
            posts = fetch_wp_posts_page(page)
            if not posts:
                logger.info(f"No more posts at page {page}, stopping.")
                break

            logger.info(f"Processing page {page} ({len(posts)} posts)")

            for post in posts:
                partner_ids = post.get("partner", [])
                if not partner_ids:
                    continue

                partner_name = fetch_partner_name(partner_ids[0])
                if not partner_name:
                    continue

                post_id = post.get("id")
                original_id = f"infoamazonia_pt_{post_id}"
                article_url = post.get("link", "")

                # Look up in DB
                article = (
                    db.query(models.Article)
                    .filter(
                        (models.Article.original_id == original_id) |
                        (models.Article.url == article_url)
                    )
                    .first()
                )

                if not article:
                    logger.debug(f"Article {original_id} not in DB, skipping")
                    not_found += 1
                    continue

                if article.news_source == partner_name:
                    logger.debug(f"Article {original_id} already has correct source '{partner_name}', skipping")
                    skipped += 1
                    continue

                logger.info(
                    f"Article {original_id}: '{article.news_source}' → '{partner_name}' | {article_url}"
                )

                if args.dry_run:
                    updated += 1
                    continue

                # Fetch content via Firecrawl
                content = scrape_with_firecrawl(article_url)
                if not content:
                    logger.warning(f"Firecrawl returned nothing for {article_url}, updating source only")
                    firecrawl_failed += 1

                article.news_source = partner_name

                if content:
                    article.content = content
                    try:
                        summary, embedding = regenerate_summary_and_embedding(article.title, content)
                        article.summary_content = summary
                        article.embedding = embedding
                    except Exception as e:
                        logger.error(f"Failed to regenerate summary/embedding for {original_id}: {e}")

                db.commit()
                updated += 1

    finally:
        db.close()

    action = "Would update" if args.dry_run else "Updated"
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Done.")
    print(f"  {action}: {updated}")
    print(f"  Already correct (skipped): {skipped}")
    print(f"  Not in DB: {not_found}")
    if not args.dry_run:
        print(f"  Firecrawl failed (source updated, content unchanged): {firecrawl_failed}")


if __name__ == "__main__":
    main()
