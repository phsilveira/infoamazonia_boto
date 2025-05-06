import trafilatura
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

def get_website_text_content(url: str) -> Optional[str]:
    """
    This function takes a URL and returns the main text content of the website.
    The text content is extracted using trafilatura and is easier to understand.
    
    Returns:
        str: The extracted text content or None if extraction failed
    """
    try:
        # Send a request to the website
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            logger.error(f"Failed to download content from {url}")
            return None
            
        # Extract the main content
        text = trafilatura.extract(downloaded)
        return text
    except Exception as e:
        logger.error(f"Error extracting content from {url}: {str(e)}")
        return None

def extract_article_metadata(url: str) -> Dict[str, Any]:
    """
    Extract metadata from an article URL including title, author, date, etc.
    
    Returns:
        Dict containing metadata fields or empty dict if extraction failed
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            logger.error(f"Failed to download content from {url}")
            return {}
            
        # Extract metadata
        metadata = {}
        xml_result = trafilatura.extract(downloaded, output_format='xml', include_comments=False, 
                                        include_tables=True, include_images=False, include_links=True)
        
        if xml_result:
            # Parse title
            import re
            title_match = re.search(r'<title>(.*?)</title>', xml_result)
            if title_match:
                metadata['title'] = title_match.group(1)
                
            # Parse date if available
            date_match = re.search(r'<date>(.*?)</date>', xml_result)
            if date_match:
                metadata['published_date'] = date_match.group(1)
                
            # Parse author if available
            author_match = re.search(r'<author>(.*?)</author>', xml_result)
            if author_match:
                metadata['author'] = author_match.group(1)
                
        return metadata
    except Exception as e:
        logger.error(f"Error extracting metadata from {url}: {str(e)}")
        return {}