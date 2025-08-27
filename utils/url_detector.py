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
    Extract all URLs from the text
    """
    # URL pattern to match common URL formats
    url_pattern = r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:\w*))?)?'
    
    # Alternative pattern for URLs without protocol
    simple_url_pattern = r'(?:www\.)?[\w\-\.]+\.[\w]{2,}(?:/[\w\-\.]*)*(?:\?[\w&=%]*)?(?:#\w*)?'
    
    urls = []
    
    # Find URLs with protocol
    urls.extend(re.findall(url_pattern, text, re.IGNORECASE))
    
    # Find URLs without protocol
    simple_urls = re.findall(simple_url_pattern, text, re.IGNORECASE)
    for url in simple_urls:
        if not any(full_url in url for full_url in urls):  # Avoid duplicates
            urls.append(url)
    
    return urls