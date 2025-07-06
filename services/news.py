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

    def get_news(self, page_limit=3, offset=0):
        """Fetch the latest news from the APIs and process them."""
        documents = []
        api_error_count = 0
        total_apis = len(self.api_sources)

        for api in self.api_sources:
            api_source = api.get("api_source")
            api_url = api.get("api_url")
            lang = api.get("lang")

            try:
                # First check if the API is accessible
                response = requests.get(api_url)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                logging.error(f"Error connecting to {api_url}: {e}")
                api_error_count += 1
                continue

            try:
                # Determine page count
                headers = response.headers
                if int(headers.get("X-WP-TotalPages", 1)) > page_limit:
                    number_of_pages = page_limit
                else:
                    number_of_pages = int(headers.get("X-WP-TotalPages", 1))

                # Process each page
                for page in range(1, number_of_pages + 1):  # Changed to start from 1 instead of 0
                    api_url_page = f"{api_url}?_embed=wp:term&per_page=10&page={page}"
                    try:
                        response = requests.get(api_url_page)
                        response.raise_for_status()

                        logging.info(f"API: {api_source}, Page {page}")
                        for item in response.json():
                            news = self.process_news_item(item, api_source)
                            if news and not self.is_duplicate_news(news):
                                documents.append(news)
                    except requests.exceptions.RequestException as e:
                        logging.error(f"Error fetching page {page} from {api_url}: {e}")
                        continue
                    except ValueError as e:
                        # Handle JSON parsing errors
                        logging.error(f"Error parsing JSON from {api_url}, page {page}: {e}")
                        continue
            except Exception as e:
                logging.error(f"Unexpected error processing {api_source}: {e}")
                api_error_count += 1

        # Return appropriate response based on results
        if documents:
            return {
                "success": True,
                "news": documents,
                "number_of_news": len(documents),
            }
        elif api_error_count == total_apis:
            # All APIs failed
            return {
                "success": False,
                "message": "All news sources failed to respond"
            }
        else:
            # No new articles found but APIs responded
            return {
                "success": True,
                "news": [],
                "number_of_news": 0,
                "message": "No new articles found"
            }

    def process_news_item(self, item, api_source):
        """Process a single news item."""
        news = {}
        meta = item.get("meta")
        location = meta.get("_related_point") if meta else None
        location_dict = self.process_location(location)

        news["success"] = True
        news["_id"] = f"{api_source}_{item.get('id')}"
        news["collection_date"] = datetime.now(pytz.timezone("America/Sao_Paulo"))
        news["location"] = location_dict

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
            self.set_source(news)

            content = item.get('content', {}).get('rendered', '')
            soup = BeautifulSoup(content, 'html.parser')
            news['content'] = soup.get_text()

            if news["success"]:
                self.get_topics(news)
                return news

        # Get the article URL from the item
        article_url = item.get("link", "")
        if not article_url:
            news["success"] = False
            return None

        try:
            # Fetch the article page
            response = requests.get(article_url, timeout=10)
            response.raise_for_status()

            # Parse the HTML content
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract metadata from meta tags
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

            self.set_source(news)

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

    def set_source(self, news):
        """Set the source of the news item."""
        if "//infoamazonia.org/" in news["URL"]:
            news["news_source"] = "infoamazonia.org"
        elif "//plenamata.eco/" in news["URL"]:
            news["news_source"] = "plenamata.eco"
        else:
            news["news_source"] = ""
            news["success"] = False

    def check_news_field(self, api_dict, news, field, field_name, empty):
        """Check and set a field in the news item."""
        try:
            news[field_name] = api_dict.get(field, empty)
            if not news[field_name] and field in ["title", "description", "URL"]:
                news["success"] = False
        except Exception as e:
            logging.error(f"{field} exception: {e}")
            news[field_name] = empty
            if field in ["title", "description", "URL"]:
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
