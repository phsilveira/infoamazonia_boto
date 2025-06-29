#!/usr/bin/env python3
"""
Test script to validate the search API fix for keyword parsing
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.search import search_term_service
from database import SessionLocal
import json

async def test_search_fix():
    """Test the search function to ensure keywords are properly parsed as lists"""
    print("Testing search fix for keyword parsing...")
    
    # Create database session
    db = SessionLocal()
    
    try:
        # First, let's check what articles exist
        from sqlalchemy import text
        result_check = db.execute(text("SELECT id, title, keywords FROM articles LIMIT 5")).fetchall()
        print(f"Found {len(result_check)} articles in database:")
        for article in result_check:
            print(f"  - {article.title}")
            print(f"    Keywords (raw): {article.keywords}")
            
        # Test search with a query from actual article titles
        test_queries = ["amazonia", "brasil", "governo"]
        
        for query in test_queries:
            print(f"\n--- Testing query: '{query}' ---")
            result = await search_term_service(
                query=query,
                db=db,
                generate_summary=False  # Disable summary generation to focus on keywords fix
            )
            
            print(f"Search successful: {result['success']}")
            print(f"Number of results: {result['count']}")
            
            if result['results']:
                # Check first few results for keyword format
                for i, article in enumerate(result['results'][:2]):
                    print(f"\nArticle {i+1}:")
                    print(f"  Title: {article['title']}")
                    print(f"  Keywords type: {type(article['key_words'])}")
                    print(f"  Keywords value: {article['key_words']}")
                    
                    # Validate that keywords is a list
                    if isinstance(article['key_words'], list):
                        print(f"  ✅ Keywords correctly parsed as list with {len(article['key_words'])} items")
                    else:
                        print(f"  ❌ Keywords not parsed correctly, got {type(article['key_words'])}")
                        return False
                        
                # Test passed for this query, move to next
                break
            else:
                print(f"  No results found for '{query}'")
        
        print("\n✅ All tests passed! Keywords are now properly parsed as lists.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = asyncio.run(test_search_fix())
    sys.exit(0 if success else 1)