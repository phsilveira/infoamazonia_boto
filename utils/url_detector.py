import re
from typing import List
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

def remove_utm_parameters(url: str) -> str:
    """
    Remove UTM tracking parameters from a URL.
    
    UTM parameters include: utm_source, utm_medium, utm_campaign, utm_term, utm_content, utm_id
    
    Args:
        url: The original URL that may contain UTM parameters
        
    Returns:
        The URL without UTM parameters
    """
    if not url:
        return url
        
    try:
        # Parse the URL into components
        parsed = urlparse(url)
        
        # Parse query parameters
        query_params = parse_qs(parsed.query)
        
        # Remove UTM parameters (case insensitive)
        utm_params = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'utm_id'}
        filtered_params = {
            key: value for key, value in query_params.items()
            if key.lower() not in utm_params
        }
        
        # Reconstruct query string
        new_query = urlencode(filtered_params, doseq=True) if filtered_params else ''
        
        # Reconstruct the URL
        new_parsed = parsed._replace(query=new_query)
        cleaned_url = urlunparse(new_parsed)
        
        return cleaned_url
        
    except Exception:
        # If URL parsing fails, return original URL
        return url

def is_url(text: str) -> bool:
    """
    Check if the text contains a URL
    """
    # URL pattern to match common URL formats - improved to handle hyphens and more characters
    url_pattern = r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_\.\-~:@!$&\'()*+,;=%])*(?:\?(?:[\w&=%\.#\-~:@!$\'()*+,;/]*)*)?(?:\#(?:[\w\-~:@!$&\'()*+,;=%\.]*))?)?'
    
    # Alternative pattern for URLs without protocol - improved to handle hyphens and more characters  
    simple_url_pattern = r'(?:www\.)?[\w\-\.]+\.[\w]{2,}(?:/[\w\-\.~:@!$&\'()*+,;=%]*)*(?:\?[\w&=%\.#\-~:@!$\'()*+,;/]*)?(?:\#[\w\-~:@!$&\'()*+,;=%]*)?'
    
    return bool(re.search(url_pattern, text, re.IGNORECASE)) or bool(re.search(simple_url_pattern, text, re.IGNORECASE))

def extract_urls(text: str) -> List[str]:
    """
    Extract and normalize all URLs from the text, removing duplicates
    """
    # URL pattern to match common URL formats - improved to handle hyphens and more characters
    url_pattern = r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_\.\-~:@!$&\'()*+,;=%])*(?:\?(?:[\w&=%\.#\-~:@!$\'()*+,;/]*)*)?(?:\#(?:[\w\-~:@!$&\'()*+,;=%\.]*))?)?'
    
    # Alternative pattern for URLs without protocol - improved to handle hyphens and more characters  
    simple_url_pattern = r'(?:www\.)?[\w\-\.]+\.[\w]{2,}(?:/[\w\-\.~:@!$&\'()*+,;=%]*)*(?:\?[\w&=%\.#\-~:@!$\'()*+,;/]*)?(?:\#[\w\-~:@!$&\'()*+,;=%]*)?'
    
    urls = []
    normalized_urls = set()  # To track normalized versions and avoid duplicates
    
    # Find URLs with protocol first
    protocol_urls = re.findall(url_pattern, text, re.IGNORECASE)
    for url in protocol_urls:
        # Remove UTM parameters before processing
        clean_url = remove_utm_parameters(url)
        normalized = normalize_url(clean_url)
        if normalized and normalized not in normalized_urls:
            urls.append(clean_url)  # Store cleaned URL
            normalized_urls.add(normalized)
    
    # Find URLs without protocol
    simple_urls = re.findall(simple_url_pattern, text, re.IGNORECASE)
    for url in simple_urls:
        # Add https:// prefix for normalization check
        full_url = f"https://{url}" if not url.startswith(('http://', 'https://')) else url
        # Remove UTM parameters before processing
        clean_full_url = remove_utm_parameters(full_url)
        normalized = normalize_url(clean_full_url)
        if normalized and normalized not in normalized_urls:
            # Return cleaned URL in original format (with or without protocol)
            clean_display_url = clean_full_url.replace("https://", "") if not url.startswith(('http://', 'https://')) else clean_full_url
            urls.append(clean_display_url)
            normalized_urls.add(normalized)
    
    return urls

def normalize_url(url: str) -> str:
    """
    Normalize a URL for duplicate detection
    """
    if not url:
        return ""
    
    # Ensure protocol
    if not url.startswith(('http://', 'https://')):
        url = f"https://{url}"
    
    # Convert to lowercase for comparison
    url = url.lower()
    
    # Remove trailing slash
    if url.endswith('/'):
        url = url[:-1]
    
    return url