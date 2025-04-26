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

# Load environment variables
load_dotenv()

# API Keys and credentials
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

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
        # Append "news" to the query to prioritize news articles
        search_query = f"{query} news"
        
        # Google Search API URL
        url = "https://www.googleapis.com/customsearch/v1"
        
        # Parameters for the search
        params = {
            "key": GOOGLE_API_KEY,
            "cx": GOOGLE_SEARCH_ENGINE_ID,
            "q": search_query,
            "num": num_results,
            "sort": "date",  # Sort by date to get recent articles
            "dateRestrict": "d7",  # Restrict to the last 7 days
        }
        
        # Make the request
        response = requests.get(url, params=params)
        
        # Check if request was successful
        if response.status_code != 200:
            print(f"Error searching Google: {response.status_code}")
            print(response.text)
            return []
        
        # Parse the response
        search_results = response.json()
        
        # Extract articles from the search results
        articles = []
        
        if "items" in search_results:
            for item in search_results["items"]:
                title = item.get("title", "")
                link = item.get("link", "")
                snippet = item.get("snippet", "")
                
                # Try to extract source from the display link or pagemap
                source = item.get("displayLink", "")
                
                # Try to extract publication date if available
                published = None
                if "pagemap" in item and "metatags" in item["pagemap"]:
                    for metatag in item["pagemap"]["metatags"]:
                        if "article:published_time" in metatag:
                            published = metatag["article:published_time"]
                            break
                
                articles.append(Article(title, link, snippet, source, published))
        
        return articles
    except Exception as e:
        print(f"Error searching Google: {str(e)}")
        return []

def fetch_top_fashion_news() -> List[Dict[str, Any]]:
    """
    Fetches top 5 fashion news articles using Google Search API.
    """
    articles = search_google_news("top fashion trends", 5)
    return [article.to_dict() for article in articles]

@app.post("/api/digest")
async def create_digest(req: DigestRequest):
    # 1. Validate input
    topic = req.topic
    phone_number = req.phone_number
    
    if not topic or not phone_number:
        raise HTTPException(status_code=400, detail="Topic and phone number are required")
    
    # 2. Fetch news articles - default to fashion if no specific topic
    if topic.lower() in ["fashion", "style", "clothing", "apparel"]:
        articles = fetch_top_fashion_news()
    else:
        raw_articles = search_google_news(topic, 5)
        articles = [article.to_dict() for article in raw_articles]
    
    # 3. Format digest
    digest = f"📰 DAILY DIGEST: {topic.upper()} 📰\n\n"
    
    if not articles:
        digest += "No recent news found for this topic. Try again later or try a different topic."
    else:
        for i, article in enumerate(articles, 1):
            digest += f"{i}. {article['title']}\n"
            digest += f"   {article['snippet'][:100]}...\n"
            digest += f"   Read more: {article['link']}\n\n"
    
    digest += "\nPowered by Cascade Digest"
    
    # 4. Send SMS via Twilio (placeholder for now)
    # This would use the Twilio SDK to send the digest as SMS
    # Example: client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    #          message = client.messages.create(body=digest, from_=TWILIO_PHONE_NUMBER, to=phone_number)
    sms_status = "sent (placeholder)"
    
    return {
        "status": "digest_sent",
        "topic": topic,
        "phone_number": phone_number,
        "digest": digest,
        "sms_status": sms_status,
        "articles": articles
    }

@app.get("/api/fashion-news")
async def get_fashion_news():
    """
    Endpoint to get top 5 fashion news articles.
    """
    articles = fetch_top_fashion_news()
    return {"articles": articles}

@app.get("/api/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)