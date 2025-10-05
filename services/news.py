#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pprint
import pytz
import requests
from bs4 import BeautifulSoup
import logging
from datetime import datetime


pp = pprint.PrettyPrinter(indent=4)
logging.basicConfig(level=logging.INFO)

class News:
    def __init__(self, news_source=None):
        if news_source:
            # Use the provided news source URL
            self.api_sources = [
                {
                    "api_source": f"{news_source.name.lower().replace(' ', '_')}",
                    "lang": "pt",  # Default to Portuguese, could be made configurable
                    "api_url": f"{news_source.url.rstrip('/')}/wp-json/wp/v2/posts",
                    "news_source_name": news_source.name
                }
            ]
        else:
            # Fallback to default sources if no specific source provided
            self.api_sources = [
                {
                    "api_source": "infoamazonia_pt",
                    "lang": "pt",
                    "api_url": "https://infoamazonia.org/wp-json/wp/v2/posts",
                }
            ]

    def get_news(self, page_limit=2, offset=0):
        """Fetch the latest news from the APIs and process them."""
        documents = []
        api_error_count = 0
        total_apis = len(self.api_sources)

        for api in self.api_sources:
            news_source_name = api.get("news_source_name")
            api_source = api.get("api_source")
            api_url = api.get("api_url")

            logging.info(f"Starting to fetch news from {news_source_name} ({api_url})")

            try:
                posts = self._fetch_posts_from_api(api_url, page_limit)
                if not posts:
                    logging.warning(f"No posts retrieved from {news_source_name}")
                    api_error_count += 1
                    continue

                logging.info(f"Retrieved {len(posts)} posts from {news_source_name}")

                # Process posts and stop if duplicates are found
                for post in posts:
                    news = self.process_news_item(post, api_source, news_source_name)
                    if news:  # Only add if processing was successful
                        if self.is_duplicate_news(news):
                            logging.info(f"Duplicate found for {news['_id']}, stopping fetch for this source")
                            break  # Stop processing more posts from this source
                        documents.append(news)

            except Exception as e:
                logging.error(f"Failed to fetch news from {news_source_name}: {e}")
                api_error_count += 1

        # Return appropriate response based on results
        if documents:
            return {
                "success": True,
                "news": documents,
                "number_of_news": len(documents),
            }
        elif api_error_count == total_apis:
            return {
                "success": False,
                "message": "All news sources failed to respond"
            }
        else:
            return {
                "success": True,
                "news": [],
                "number_of_news": 0,
                "message": "No new articles found"
            }

    def _fetch_posts_from_api(self, api_url, page_limit):
        """Fetch posts from a WordPress API with proper pagination and error handling."""
        all_posts = []

        # Standard headers for WordPress API requests - simplified to avoid compression issues
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9,pt;q=0.8',
            'Connection': 'keep-alive',
        }

        # First, test if the API is accessible and get total pages
        try:
            response = self._make_api_request(api_url, headers)
            if not response:
                return []

            # Get total pages from headers
            total_pages = int(response.headers.get("X-WP-TotalPages", 1))
            pages_to_fetch = min(total_pages, page_limit)

            logging.info(f"API has {total_pages} total pages, fetching {pages_to_fetch} pages")

        except Exception as e:
            logging.error(f"Failed to connect to API {api_url}: {e}")
            return []

        # Fetch posts from each page
        for page in range(1, pages_to_fetch + 1):
            try:
                page_posts = self._fetch_posts_from_page(api_url, page, headers)
                if page_posts:
                    all_posts.extend(page_posts)
                    logging.info(f"Fetched {len(page_posts)} posts from page {page}")
                else:
                    logging.warning(f"No posts found on page {page}")

            except Exception as e:
                logging.error(f"Failed to fetch page {page} from {api_url}: {e}")
                continue

        return all_posts

    def _make_api_request(self, url, headers, timeout=30):
        """Make a single API request with proper error handling."""
        try:
            # Remove Accept-Encoding to avoid compression issues, or handle it properly
            headers_copy = headers.copy()
            headers_copy['Accept-Encoding'] = 'identity'  # Request uncompressed response

            response = requests.get(url, headers=headers_copy, timeout=timeout)
            response.raise_for_status()

            # Set encoding explicitly if not set
            if response.encoding is None:
                response.encoding = 'utf-8'

            # Validate JSON response
            try:
                # Try to decode the response text first
                content = response.text
                if not content.strip():
                    logging.error(f"Empty response from {url}")
                    return None

                # Try to parse JSON
                json_data = response.json()
                return response

            except UnicodeDecodeError as e:
                logging.error(f"Unicode decode error from {url}: {e}")
                # Try different encodings
                for encoding in ['utf-8', 'latin-1', 'iso-8859-1']:
                    try:
                        response.encoding = encoding
                        response.json()
                        logging.info(f"Successfully decoded with {encoding} encoding")
                        return response
                    except (UnicodeDecodeError, ValueError):
                        continue
                return None

            except ValueError as e:
                logging.error(f"Invalid JSON response from {url}: {e}")
                logging.error(f"Content type: {response.headers.get('content-type', 'unknown')}")
                logging.error(f"Response encoding: {response.encoding}")

                # Try to decode response with different methods
                try:
                    # Try raw content
                    raw_text = response.content.decode('utf-8', errors='ignore')
                    logging.error(f"Raw content preview: {raw_text[:200]}...")
                except Exception as decode_error:
                    logging.error(f"Could not decode raw content: {decode_error}")

                return None

        except requests.exceptions.Timeout:
            logging.error(f"Timeout connecting to {url}")
            return None
        except requests.exceptions.ConnectionError:
            logging.error(f"Connection error to {url}")
            return None
        except requests.exceptions.HTTPError as e:
            logging.error(f"HTTP error {e.response.status_code} from {url}")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Request error to {url}: {e}")
            return None

    def _fetch_posts_from_page(self, api_url, page, headers):
        """Fetch posts from a specific page."""
        page_url = f"{api_url}?page={page}&per_page=10"

        response = self._make_api_request(page_url, headers)
        if not response:
            return []

        try:
            posts_data = response.json()

            if not isinstance(posts_data, list):
                logging.error(f"Expected list response from {page_url}, got {type(posts_data)}")
                return []

            return posts_data

        except ValueError as e:
            logging.error(f"Failed to parse JSON from {page_url}: {e}")
            return []

    def process_news_item(self, item, api_source, news_source_name):
        """Process a single news item."""
        news = {}

        # Check if this is the new format (has title.rendered) or old format (has yoast_head_json)
        is_new_format = 'title' in item and isinstance(item['title'], dict) and 'rendered' in item['title']

        if is_new_format:
            # Process new format (Alente-style)
            return self.process_new_format_item(item, api_source, news_source_name)
        else:
            # Process old format (InfoAmazonia-style)
            return self.process_old_format_item(item, api_source, news_source_name)

    def process_new_format_item(self, item, api_source, news_source_name):
        """Process news item in new format (title.rendered, content.rendered structure)."""
        news = {}
        news["success"] = True
        news["news_source"] = news_source_name
        news["_id"] = f"{api_source}_{item.get('id')}"
        news["collection_date"] = datetime.now(pytz.timezone("America/Sao_Paulo"))

        # No location data in new format
        news["location"] = {"location": False}
        meta = item.get("meta")
        location = meta.get("_related_point") if meta else None
        location_dict = self.process_location(location)
        news["location"] = {"location": location_dict}

        # Extract basic fields from new format
        title_obj = item.get('title', {})
        news['Title'] = title_obj.get('rendered', '') if isinstance(title_obj, dict) else str(title_obj)

        # Extract description from excerpt
        excerpt_obj = item.get('excerpt', {})
        excerpt_html = excerpt_obj.get('rendered', '') if isinstance(excerpt_obj, dict) else str(excerpt_obj)
        soup = BeautifulSoup(excerpt_html, "html.parser")
        news['Description'] = soup.get_text().strip()
        news['description'] = news['Description']  # Keep both for compatibility

        # Extract content
        content_obj = item.get('content', {})
        content_html = content_obj.get('rendered', '') if isinstance(content_obj, dict) else str(content_obj)
        soup = BeautifulSoup(content_html, 'html.parser')
        news['content'] = soup.get_text().strip()

        # Set other required fields
        news['URL'] = item.get('link', '')
        news['Published_date'] = item.get('date', '')
        news['Author'] = ''  # Not directly available in this format
        news['Language'] = 'pt'  # Default to Portuguese
        news['site'] = news_source_name

        # Fetch categories for Keywords
        post_id = item.get('id')
        news['Keywords'] = self.fetch_categories(post_id, news_source_name)
        news['Subtopics'] = self.fetch_tags(post_id, news_source_name)

        # Validate required fields
        if not news['Title'] or not news['URL']:
            news["success"] = False
            return None

        if news["success"]:
            self.get_topics(news)
            return news

        return None

    def fetch_categories(self, post_id, news_source_name):
        """Fetch categories for a post from WordPress API."""
        if not post_id:
            return []

        try:
            # Extract base URL from the api_sources
            base_url = None
            for api_source in self.api_sources:
                if api_source.get("news_source_name") == news_source_name:
                    api_url = api_source.get("api_url", "")
                    # Extract base URL by removing the wp-json path
                    if "/wp-json/wp/v2/posts" in api_url:
                        base_url = api_url.replace("/wp-json/wp/v2/posts", "")
                        break

            if not base_url:
                return []

            categories_url = f"{base_url}/wp-json/wp/v2/categories?post={post_id}"

            # Use the improved API request method
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9,pt;q=0.8',
                'Connection': 'keep-alive',
            }

            response = self._make_api_request(categories_url, headers, timeout=10)
            if not response:
                return []

            categories_data = response.json()

            # Extract category names
            category_names = []
            if isinstance(categories_data, list):
                for category in categories_data:
                    if isinstance(category, dict) and 'name' in category:
                        category_names.append(category['name'])

            return category_names

        except Exception as e:
            logging.error(f"Unexpected error fetching categories for post {post_id}: {e}")
            return []

    def fetch_tags(self, post_id, news_source_name):
        """Fetch tags for a post from WordPress API."""
        if not post_id:
            return []

        try:
            # Extract base URL from the api_sources
            base_url = None
            for api_source in self.api_sources:
                if api_source.get("news_source_name") == news_source_name:
                    api_url = api_source.get("api_url", "")
                    # Extract base URL by removing the wp-json path
                    if "/wp-json/wp/v2/posts" in api_url:
                        base_url = api_url.replace("/wp-json/wp/v2/posts", "")
                        break

            if not base_url:
                return []

            tags_url = f"{base_url}/wp-json/wp/v2/tags?post={post_id}"

            # Use the improved API request method
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9,pt;q=0.8',
                'Connection': 'keep-alive',
            }

            response = self._make_api_request(tags_url, headers, timeout=10)
            if not response:
                return []

            tags_data = response.json()

            # Extract tag names
            tag_names = []
            if isinstance(tags_data, list):
                for tag in tags_data:
                    if isinstance(tag, dict) and 'name' in tag:
                        tag_names.append(tag['name'])

            return tag_names

        except Exception as e:
            logging.error(f"Unexpected error fetching tags for post {post_id}: {e}")
            return []

    def process_old_format_item(self, item, api_source, news_source_name):
        """Process news item in old format (InfoAmazonia-style with yoast_head_json)."""
        news = {}
        meta = item.get("meta")
        location = meta.get("_related_point") if meta else None
        location_dict = self.process_location(location)

        news["success"] = True
        news["news_source"] = news_source_name
        news["_id"] = f"{api_source}_{item.get('id')}"
        news["collection_date"] = datetime.now(pytz.timezone("America/Sao_Paulo"))
        news["location"] = location_dict

        soup = BeautifulSoup(item.get('excerpt', {}).get('rendered', ''), "html.parser")
        description = soup.get_text()
        news['description'] = description

        yoast = item.get("yoast_head_json")
        if yoast:
            self.check_news_field(yoast, news, "og_title", "Title", "")
            self.check_news_field(yoast, news, "article_published_time", "Published_date", "")
            self.check_news_field(yoast, news, "author", "Author", "")
            self.check_news_field(yoast, news, "description", "Description", "")
            self.check_news_field(yoast, news, "og_url", "URL", "")
            self.check_news_field(yoast, news, "og_site_name", "site", "")
            schema = yoast.get("schema", {}).get("@graph", [{}])[0]
            self.check_news_field(schema, news, "articleSection", "Subtopics", [])
            self.check_news_field(schema, news, "keywords", "Keywords", [])
            self.check_news_field(schema, news, "inLanguage", "Language", "")
            content = item.get('content', {}).get('rendered', '')
            soup = BeautifulSoup(content, 'html.parser')
            news['content'] = soup.get_text()

            if news["success"]:
                self.get_topics(news)
                return news

        # Fallback: scrape article page if yoast data not available
        article_url = item.get("link", "")
        if not article_url:
            news["success"] = False
            return None

        try:
            # Add headers for web scraping
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,pt;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
            }

            # Fetch the article page
            response = requests.get(article_url, timeout=10, headers=headers)
            response.raise_for_status()

            # Parse the HTML content
            soup = BeautifulSoup(response.text, 'html.parser')
            meta_tags = {}

            # Get Open Graph and other meta tags
            og_title = soup.find("meta", property="og:title")
            if og_title:
                meta_tags["og_title"] = og_title.get("content", "")

            og_description = soup.find("meta", property="og:description")
            if og_description:
                meta_tags["description"] = og_description.get("content", "")

            og_url = soup.find("meta", property="og:url")
            if og_url:
                meta_tags["og_url"] = og_url.get("content", "")

            og_site_name = soup.find("meta", property="og:site_name")
            if og_site_name:
                meta_tags["og_site_name"] = og_site_name.get("content", "")

            article_published_time = soup.find("meta", property="article:published_time")
            if article_published_time:
                meta_tags["article_published_time"] = article_published_time.get("content", "")

            author_meta = soup.find("meta", attrs={"name": "author"})
            if author_meta:
                meta_tags["author"] = author_meta.get("content", "")

            # Try to get language from html lang attribute
            html_tag = soup.find("html")
            if html_tag and html_tag.get("lang"):
                meta_tags["inLanguage"] = html_tag.get("lang", "")

            # Extract structured data from JSON-LD
            json_ld_scripts = soup.find_all("script", type="application/ld+json")
            keywords = []
            subtopics = []

            for script in json_ld_scripts:
                try:
                    import json
                    data = json.loads(script.string)
                    if isinstance(data, dict) and "@graph" in data:
                        for item_data in data["@graph"]:
                            if item_data.get("@type") == "NewsArticle":
                                if "keywords" in item_data:
                                    if isinstance(item_data["keywords"], list):
                                        keywords = item_data["keywords"]
                                    else:
                                        keywords = [item_data["keywords"]]
                                if "articleSection" in item_data:
                                    if isinstance(item_data["articleSection"], list):
                                        subtopics = item_data["articleSection"]
                                    else:
                                        subtopics = [item_data["articleSection"]]
                                break
                except (json.JSONDecodeError, KeyError):
                    continue

            # Set the extracted fields
            news["Title"] = meta_tags.get("og_title", "")
            news["Description"] = meta_tags.get("description", "")
            news["URL"] = meta_tags.get("og_url", article_url)
            news["site"] = meta_tags.get("og_site_name", "")
            news["Published_date"] = meta_tags.get("article_published_time", "")
            news["Author"] = meta_tags.get("author", "")
            news["Language"] = meta_tags.get("inLanguage", "")
            news["Keywords"] = keywords
            news["Subtopics"] = subtopics

            # Extract article content
            # Try to find the main content area
            content_selectors = [
                "article .entry-content",
                ".post-content",
                ".article-content",
                "[class*='content']",
                "main"
            ]

            content_text = ""
            for selector in content_selectors:
                content_element = soup.select_one(selector)
                if content_element:
                    content_text = content_element.get_text(strip=True)
                    break

            # Fallback to getting all paragraph text
            if not content_text:
                paragraphs = soup.find_all("p")
                content_text = " ".join([p.get_text(strip=True) for p in paragraphs])

            news["content"] = content_text

            # Validate required fields
            if not news["Title"] or not news["URL"]:
                news["success"] = False
                return None

            if news["success"]:
                self.get_topics(news)
                return news

        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching article {article_url}: {e}")
            news["success"] = False
            return None
        except Exception as e:
            logging.error(f"Error processing article {article_url}: {e}")
            news["success"] = False
            return None

        return None

    def process_location(self, location):
        """Process the location information."""
        location_dict = {"location": bool(location)}
        if location:
            try:
                location_dict.update({
                    "lat": location[0].get("_geocode_lat"),
                    "lon": location[0].get("_geocode_lon"),
                    "country": location[0].get("_geocode_country"),
                    "region": location[0].get("_geocode_region_level_1"),
                    "state": location[0].get("_geocode_region_level_2"),
                    "metropolitan": location[0].get("_geocode_region_level_3"),
                    "city": location[0].get("_geocode_city"),
                    "city_region": location[0].get("_geocode_city_level_1"),
                    "address": location[0].get("_geocode_full_address"),
                })
            except (IndexError, AttributeError):
                location_dict["location"] = False
        return location_dict

    def check_news_field(self, api_dict, news, field, field_name, empty):
        """Check and set a field in the news item."""
        try:
            news[field_name] = api_dict.get(field, empty)
            if not news[field_name] and field in ["title", "URL"]:
                news["success"] = False
        except Exception as e:
            logging.error(f"{field} exception: {e}")
            news[field_name] = empty
            if field in ["title", "URL"]:
                news["success"] = False

    def get_topics(self, news):
        """Determine the topics of the news item."""
        topics_mapping = {
            "danos_ambientais": [
                "Desmatamento", "Queimadas", "Garimpo", "Mineração", "Grilagem",
                "Agronegócio", "Agropecuária", "Madeira", "Poluição", "Petróleo",
                "Pecuária", "Crime ambiental", "Estradas", "Água", "Hidrelétricas",
                "Sistemas de Monitoramento"
            ],
            "areas_protegidas": [
                "Áreas Protegidas", "Unidades de Conservação", "Terras indígenas",
                "Pantanal", "Questão fundiária", "Indígenas"
            ],
            "povos": [
                "Cultura", "Covid-19", "Saúde", "Defensores ambientais", "Memória",
                "Quilombolas", "Mulher", "Emigrar", "Educação", "Paz e Guerra",
                "Religião", "Indígenas"
            ],
            "mudanca_climatica": ["Mudança climática", "Crédito de carbono", "COP27", "COP"],
            "conservacao": [
                "Biodiversidade", "Ciência", "Sistemas de Monitoramento",
                "Conservação", "Regeneração"
            ],
            "politica_economia": [
                "Sustentabilidade", "Política", "Política pública", "Bioeconomia",
                "Eleições 2022", "Eleições", "Corrupção", "Produtos sustentáveis",
                "Milícia", "Congresso Nacional", "Supremo"
            ]
        }

        news_subtopics = set(news.get("Subtopics", []))
        news_topics = [
            topic for topic, keywords in topics_mapping.items()
            if news_subtopics.intersection(keywords) or ("plenamata" in news["news_source"] and topic == "danos_ambientais")
        ]
        news["News_topics"] = news_topics

    def is_duplicate_news(self, news):
        """Check if the news item is a duplicate using database query."""
        from models import Article

        # Allow accessing db passed from the caller, or use mock in case it's not provided
        if hasattr(self, 'db'):
            db = self.db
            # Use the provided db session
            existing = db.session.query(Article).filter(
                (Article.original_id == news["_id"]) |
                (Article.url == news["URL"])
            ).first()
        else:
            # Original approach - only works in Flask app context
            from app import db
            existing = Article.query.filter(
                (Article.original_id == news["_id"]) |
                (Article.url == news["URL"])
            ).first()

        return existing is not None