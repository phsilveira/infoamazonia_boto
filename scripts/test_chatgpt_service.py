#!/usr/bin/env python3
"""
Test script for the ChatGPT service with Azure support.
This script can be run to test integration with both standard OpenAI
and Azure OpenAI.

To run with standard OpenAI:
python test_chatgpt_service.py

To run with Azure OpenAI:
USE_AZURE_OPENAI=True python test_chatgpt_service.py
"""

import os
import sys
import asyncio
from services.chatgpt import ChatGPTService

# Override settings for testing if needed
if os.getenv("USE_AZURE_OPENAI") == "True":
    os.environ["USE_AZURE_OPENAI"] = "True"
    print("Using Azure OpenAI for testing")
    
    # Make sure Azure-specific env vars are set
    required_vars = [
        "AZURE_OPENAI_API_KEY",
        "ENDPOINT_URL",
        "DEPLOYMENT_NAME"
    ]
    
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        print(f"Error: Missing required environment variables: {', '.join(missing)}")
        print("Please set these variables and try again")
        sys.exit(1)
else:
    print("Using standard OpenAI for testing")
    
    # Make sure OPENAI_API_KEY is set
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable is not set")
        print("Please set this variable and try again")
        sys.exit(1)

def test_standard_completion():
    """Test standard text completion"""
    service = ChatGPTService()
    
    response = service.generate_completion(
        query="What is the capital of France?",
        context="We're discussing European geography.",
        system_prompt="You are a helpful geography assistant."
    )
    
    print("\n=== Standard Completion ===")
    print(response)
    print("==========================\n")

async def test_streaming_completion():
    """Test streaming completion"""
    service = ChatGPTService()
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a short poem about Python programming language."}
    ]
    
    print("\n=== Streaming Completion ===")
    print("(Chunks will appear one by one)\n")
    
    # This will yield chunks
    full_response = ""
    async for chunk in service.generate_streaming_completion(messages=messages):
        print(chunk, end="", flush=True)
        full_response += chunk
    
    print("\n===========================\n")
    return full_response

def test_full_completion():
    """Test non-streaming full completion response"""
    service = ChatGPTService()
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain how to use async/await in Python in one paragraph."}
    ]
    
    print("\n=== Full Completion Response ===")
    # Using the synchronous method
    response = service.generate_completion(
        query="Explain how to use async/await in Python in one paragraph.", 
        context="", 
        system_prompt="You are a helpful coding assistant."
    )
    print(response)
    print("===============================\n")
    return response

def test_image_processing():
    """Test image processing with vision capabilities"""
    import tempfile
    
    # Skip this test if there's no image to process
    test_image = os.getenv("TEST_IMAGE_PATH")
    if not test_image:
        print("\n=== Image Processing Test ===")
        print("Skipping image processing test (TEST_IMAGE_PATH not set)")
        print("============================\n")
        return None
    
    service = ChatGPTService()
    
    print("\n=== Image Processing Test ===")
    response = service.process_image(
        image_path=test_image,
        prompt="Describe what you see in this image in detail.",
        system_prompt="You are a helpful image analysis assistant."
    )
    print(response)
    print("============================\n")
    return response

async def main():
    """Run all tests"""
    # Test standard completion
    test_standard_completion()
    
    # Test full completion with different parameters
    test_full_completion()
    
    # Test image processing (if configured)
    test_image_processing()
    
    # Test streaming completion
    await test_streaming_completion()
    
    print("All tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())