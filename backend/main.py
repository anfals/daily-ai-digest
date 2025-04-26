from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uvicorn
import requests
import os
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import json
from datetime import datetime
import anthropic
import re
import time
from concurrent.futures import ThreadPoolExecutor
from article_parser import ArticleParser
from digest_generator import DigestGenerator

# Load environment variables
load_dotenv()

# API Keys and credentials
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# Initialize Anthropic client
claude_client = None
if ANTHROPIC_API_KEY:
    claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
else:
    print("Warning: ANTHROPIC_API_KEY not found, Claude integration disabled")

# Initialize the digest generator
digest_generator = DigestGenerator(claude_client)

app = FastAPI()

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DigestRequest(BaseModel):
    topic: str
    phone_number: str
    generate_ai_digest: bool = True

class Article:
    def __init__(self, title: str, link: str, snippet: str, source: str = None, published: str = None):
        self.title = title
        self.link = link
        self.snippet = snippet
        self.source = source
        self.published = published

    def to_dict(self):
        return {
            "title": self.title,
            "link": self.link,
            "snippet": self.snippet,
            "source": self.source,
            "published": self.published
        }

def search_google_news(query: str, num_results: int = 5) -> List[Article]:
    """
    Searches Google using their Custom Search JSON API for news articles.
    """
    try:
        # Validate API key and search engine ID
        if not GOOGLE_API_KEY or not GOOGLE_SEARCH_ENGINE_ID:
            print("Error: Google API key or search engine ID not configured")
            return []
            
        # Sanitize and validate input query
        if not query or not isinstance(query, str):
            print("Error: Invalid query")
            return []
            
        # Ensure num_results is valid
        if num_results <= 0 or num_results > 20:
            num_results = 10  # Fallback to a reasonable default
        
        # Append "news" to the query to prioritize news articles
        search_query = f"{query} news"
        
        # Google Search API URL
        url = "https://www.googleapis.com/customsearch/v1"
        
        # Parameters for the search
        params = {
            "key": GOOGLE_API_KEY,
            "cx": GOOGLE_SEARCH_ENGINE_ID,
            "q": search_query,
            "num": min(num_results, 10),  # API only allows 10 per request
            "sort": "date", 
            "dateRestrict": "d1", 
        }
        
        articles = []
        
        # Handle pagination for more than 10 results
        for start_index in range(1, num_results + 1, 10):
            if start_index > 1:
                params["start"] = start_index
            
            # Make the request with timeout
            response = requests.get(url, params=params, timeout=10)
            
            # Check if request was successful
            if response.status_code != 200:
                print(f"Error searching Google: {response.status_code}")
                print(response.text)
                break
            
            # Parse the response
            search_results = response.json()
            
            # Extract articles from the search results
            if "items" in search_results:
                for item in search_results["items"]:
                    title = item.get("title", "")
                    link = item.get("link", "")
                    snippet = item.get("snippet", "")
                    
                    # Skip if missing essential fields
                    if not title or not link:
                        continue
                    
                    # Try to extract source from the display link or pagemap
                    source = item.get("displayLink", "")
                    
                    # Try to extract publication date if available
                    published = None
                    if "pagemap" in item and "metatags" in item["pagemap"]:
                        try:
                            for metatag in item["pagemap"]["metatags"]:
                                if "article:published_time" in metatag:
                                    published = metatag["article:published_time"]
                                    break
                        except Exception as meta_error:
                            print(f"Error parsing metadata: {str(meta_error)}")
                    
                    articles.append(Article(title, link, snippet, source, published))
            
            # Stop if we didn't get a full page of results
            if "items" not in search_results or len(search_results["items"]) < 10:
                break
                
            # Check if we have enough articles
            if len(articles) >= num_results:
                articles = articles[:num_results]  # Trim to exact count
                break
        
        return articles
    except requests.exceptions.Timeout:
        print("Error: Google API request timed out")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Network error during Google API request: {str(e)}")
        return []
    except Exception as e:
        print(f"Unexpected error searching Google: {str(e)}")
        return []

def get_empty_article_response() -> List[Dict[str, Any]]:
    """
    Returns an empty article response for when no articles can be fetched.
    """
    return [{
        "title": "No articles found",
        "link": "",
        "snippet": "Could not find any articles. Please try a different search or try again later.",
        "source": "System",
        "published": datetime.now().isoformat()
    }]

def fetch_top_fashion_news() -> List[Dict[str, Any]]:
    """
    Fetches top 20 fashion news articles using Google Search API.
    Falls back to empty response if the API fails.
    """
    try:
        articles = search_google_news("top fashion trends", 20)
        result = [article.to_dict() for article in articles]
        
        # If we got no results from the API, return empty response
        if not result:
            print("No results from Google API, returning empty response")
            return get_empty_article_response()
            
        return result
    except Exception as e:
        print(f"Error fetching fashion news: {str(e)}")
        return get_empty_article_response()

def format_simple_digest(topic: str, articles: List[Dict[str, Any]]) -> str:
    """Format a simple digest without using AI"""
    digest = f"📰 DAILY DIGEST: {topic.upper()} 📰\n\n"
    
    if not articles:
        digest += "No recent news found for this topic. Try again later or try a different topic."
    else:
        # Limit to the first 5 articles for SMS (to keep the message size reasonable)
        sms_articles = articles[:5]
        for i, article in enumerate(sms_articles, 1):
            try:
                title = article.get('title', 'No title')
                snippet = article.get('snippet', 'No preview available')
                link = article.get('link', '#')
                
                digest += f"{i}. {title}\n"
                digest += f"   {snippet[:100]}...\n"
                digest += f"   Read more: {link}\n\n"
            except Exception as e:
                print(f"Error formatting article {i}: {str(e)}")
                continue
    
    digest += "\nPowered by M.A.D"
    return digest

@app.post("/api/digest")
async def create_digest(req: DigestRequest):
    try:
        # 1. Validate input
        topic = req.topic
        phone_number = req.phone_number
        
        if not topic or not phone_number:
            raise HTTPException(status_code=400, detail="Topic and phone number are required")
        
        # 2. Fetch news articles - default to fashion if no specific topic
        if topic.lower() in ["fashion", "style", "clothing", "apparel"]:
            articles = fetch_top_fashion_news()
        else:
            try:
                raw_articles = search_google_news(topic, 20)
                articles = [article.to_dict() for article in raw_articles]
                
                # If no results found, return empty response
                if not articles:
                    print(f"No results found for topic '{topic}', returning empty response")
                    articles = get_empty_article_response()
            except Exception as e:
                print(f"Error searching for topic '{topic}': {str(e)}")
                
                articles = get_empty_article_response()
        
        # Ensure articles is a valid list
        if articles is None:
            articles = []
        
        # 3. If AI digest requested, fetch article content and generate digest
        ai_digest_data = None
        if req.generate_ai_digest:
            try:
                # Fetch article content
                print(f"Fetching content for {len(articles)} articles...")
                articles_with_content = ArticleParser.fetch_multiple_articles(articles)
                
                # Generate digest with Claude
                print(f"Generating digest for topic: {topic}...")
                ai_digest_data = digest_generator.generate_digest(topic, articles_with_content)
                
                # Use AI-generated digest if available
                if ai_digest_data and ("overall_summary" in ai_digest_data or "article_highlights" in ai_digest_data):
                    # Create a formatted digest from the structured data
                    digest = f"📰 {topic.upper()} NEWS SUMMARY 📰\n\n"
                    
                    if "overall_summary" in ai_digest_data and ai_digest_data["overall_summary"]:
                        digest += f"## Latest Developments\n\n{ai_digest_data['overall_summary']}\n\n"
                    
                    if "article_highlights" in ai_digest_data and ai_digest_data["article_highlights"]:
                        digest += f"## Top Articles\n\n{ai_digest_data['article_highlights']}\n\n"
                        
                    digest += "Powered by M.A.D"
                else:
                    # Fall back to simple digest if AI generation failed
                    digest = format_simple_digest(topic, articles)
            except Exception as e:
                print(f"Error generating AI digest: {str(e)}")
                # Fall back to simple digest if AI generation failed
                digest = format_simple_digest(topic, articles)
        else:
            # Format a simple digest
            digest = format_simple_digest(topic, articles)
        
        # 4. Send SMS via Twilio (placeholder for now)
        # This would use the Twilio SDK to send the digest as SMS
        # Example: client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        #          message = client.messages.create(body=digest, from_=TWILIO_PHONE_NUMBER, to=phone_number)
        sms_status = "sent (placeholder)"
        
        result = {
            "status": "digest_sent",
            "topic": topic,
            "phone_number": phone_number,
            "digest": digest,
            "sms_status": sms_status,
            "articles": articles
        }
        
        # Add AI digest data if available
        if ai_digest_data:
            result["ai_digest"] = ai_digest_data
            
        return result
        
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions
        raise http_ex
    except Exception as e:
        print(f"Unexpected error in create_digest: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@app.get("/api/fashion-news")
async def get_fashion_news():
    """
    Endpoint to get top 20 fashion news articles.
    """
    try:
        articles = fetch_top_fashion_news()
        
        # Ensure articles is a valid list
        if articles is None:
            articles = []
            
        return {"articles": articles}
    except Exception as e:
        print(f"Unexpected error in get_fashion_news: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@app.get("/api/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)