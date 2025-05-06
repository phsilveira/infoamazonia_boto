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
    def __init__(self):
        self.api_sources = [
            {
                "api_source": "infoamazonia_pt",
                "lang": "pt",
                "api_url": "https://infoamazonia.org/wp-json/wp/v2/posts",
            }
        ]

    def get_news(self, page_limit=1, offset=0):
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
