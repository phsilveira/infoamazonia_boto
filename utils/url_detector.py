import re
from typing import List

def is_url(text: str) -> bool:
    """
    Check if the text contains a URL
    """
    # URL pattern to match common URL formats
    url_pattern = r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:\w*))?)?'
    
    # Alternative pattern for URLs without protocol
    simple_url_pattern = r'(?:www\.)?[\w\-\.]+\.[\w]{2,}(?:/[\w\-\.]*)*(?:\?[\w&=%]*)?(?:#\w*)?'
    
    return bool(re.search(url_pattern, text, re.IGNORECASE)) or bool(re.search(simple_url_pattern, text, re.IGNORECASE))

def extract_urls(text: str) -> List[str]:
    """
    Extract and normalize all URLs from the text, removing duplicates
    """
    # URL pattern to match common URL formats
    url_pattern = r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:\w*))?)?'
    
    # Alternative pattern for URLs without protocol
    simple_url_pattern = r'(?:www\.)?[\w\-\.]+\.[\w]{2,}(?:/[\w\-\.]*)*(?:\?[\w&=%]*)?(?:#\w*)?'
    
    urls = []
    normalized_urls = set()  # To track normalized versions and avoid duplicates
    
    # Find URLs with protocol first
    protocol_urls = re.findall(url_pattern, text, re.IGNORECASE)
    for url in protocol_urls:
        normalized = normalize_url(url)
        if normalized and normalized not in normalized_urls:
            urls.append(url)  # Keep original format for display
            normalized_urls.add(normalized)
    
    # Find URLs without protocol
    simple_urls = re.findall(simple_url_pattern, text, re.IGNORECASE)
    for url in simple_urls:
        # Add https:// prefix for normalization check
        full_url = f"https://{url}" if not url.startswith(('http://', 'https://')) else url
        normalized = normalize_url(full_url)
        if normalized and normalized not in normalized_urls:
            urls.append(url)  # Keep original format for display
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