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
        
        # Make direct queries without modifications for specific topics
        specific_topics = ["pope", "vatican", "catholic", "catholicism", "papacy"]
        if any(topic.lower() in query.lower() for topic in specific_topics):
            # For these topics, use the query directly without modification
            search_query = query
            print(f"Using direct query for specific topic: {search_query}")
        else:
            # Append "news" to the query to prioritize news articles for other topics
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
            
            # Make the request with timeout and retries
            max_retries = 2
            retry_count = 0
            success = False
            
            while retry_count <= max_retries and not success:
                try:
                    response = requests.get(url, params=params, timeout=15)
                    
                    # Check if request was successful
                    if response.status_code == 200:
                        success = True
                    elif response.status_code >= 500:  # Server error
                        retry_count += 1
                        if retry_count <= max_retries:
                            print(f"Server error from Google API: {response.status_code}, retrying ({retry_count}/{max_retries})")
                            time.sleep(1)  # Wait before retrying
                        else:
                            print(f"Max retries reached for Google API request")
                            break
                    else:  # Client error or other
                        print(f"Error searching Google: {response.status_code}")
                        print(response.text)
                        break
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    retry_count += 1
                    if retry_count <= max_retries:
                        print(f"Request timeout/connection error for Google API, retrying ({retry_count}/{max_retries}): {str(e)}")
                        time.sleep(1)
                    else:
                        print(f"Max retries reached for Google API request")
                        raise
            
            # If all retries failed, skip this batch
            if not success:
                print("Failed to get response from Google API, skipping this batch")
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

def generate_search_query(topic: str) -> str:
    """
    Uses Claude to generate a single optimized search query for a given topic.
    Returns a string containing the optimal search query for finding diverse, relevant articles.
    """
    # If Claude client is not available, use default query
    if not claude_client:
        print("Claude client not available, using default query")
        return f"{topic} latest news developments"
    
    try:
        # Create a prompt for Claude to generate an optimized search query
        prompt = f"""# Task: Generate an Optimized News Search Query

I need to find the most relevant and recent news articles about "{topic}".

Please generate ONE optimized search query that will help me find comprehensive news coverage. 
The query should be crafted to bring back diverse results covering multiple aspects of this topic.

Your query should:
- Be specific and targeted to yield high-quality news results
- Be optimized for news search engines
- Include the most relevant keywords related to {topic}
- Be designed to find diverse coverage (breaking news, analysis, different perspectives)
- Focus on finding English-language content
- Be concise and direct (under 8 words if possible)
- NOT include phrases like "latest" or "recent" as these don't work well with search engines
- NOT include special search operators or syntax

Format your response as a single line containing just the optimized search query.
"""

        # Call Claude API to generate query
        response = claude_client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=100,
            temperature=0.2,
            system="You are a professional search query optimizer specializing in finding recent, relevant news articles.",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # Extract the response text and clean it
        result = response.content[0].text.strip()
        
        # Remove any markdown formatting, quotes, or explanations
        # Just get the pure query
        query = result
        
        # Check for common patterns like starting with "Query:" or having quotes
        if ":" in query:
            query = query.split(":", 1)[1].strip()
        
        # Remove quotes if present
        query = query.strip('"\'')
        
        # Final validation
        if not query or len(query) < 3:
            print("Failed to generate a valid query, using default")
            return f"{topic} news developments"
            
        print(f"Generated optimized search query for topic '{topic}': '{query}'")
        return query
        
    except Exception as e:
        print(f"Error generating search query with Claude: {str(e)}")
        # Return a default query if Claude fails
        return f"{topic} news developments"

def search_with_optimized_query(topic: str) -> List[Dict[str, Any]]:
    """
    Uses Claude to generate a single optimized search query, executes it
    to gather articles, and returns the collected articles.
    """
    try:
        # Generate single optimized query using Claude
        print(f"Generating optimized search query for topic: {topic}")
        optimized_query = generate_search_query(topic)
        print(f"Using optimized query for topic '{topic}': '{optimized_query}'")
        
        # Execute the query to get articles
        print(f"Executing optimized query: {optimized_query}")
        results = search_google_news(optimized_query, 20)
        
        if results:
            # Convert articles to dictionaries
            all_articles = [article.to_dict() for article in results]
            print(f"Found {len(all_articles)} articles with optimized query")
            return all_articles
                
        # If we didn't find any articles with optimized query, try direct search
        print(f"No articles found with optimized query, trying direct search")
        direct_query = f"{topic}"
        print(f"Trying direct query: {direct_query}")
        direct_results = search_google_news(direct_query, 10)
        
        if direct_results:
            direct_articles = [article.to_dict() for article in direct_results]
            print(f"Found {len(direct_articles)} articles with direct query")
            return direct_articles
        
        # If still no results, try with "news" added explicitly
        news_query = f"{topic} news"
        print(f"Trying news query: {news_query}")
        news_results = search_google_news(news_query, 10)
        
        if news_results:
            news_articles = [article.to_dict() for article in news_results]
            print(f"Found {len(news_articles)} articles with news query")
            return news_articles
        
        # If still no articles, create a mock article with information
        print(f"No articles found for {topic} after all search attempts. Creating a mock article.")
        mock_article = {
            "title": f"Information about {topic}",
            "link": f"https://en.wikipedia.org/wiki/{topic.replace(' ', '_')}",
            "snippet": f"We couldn't find recent news articles specifically about {topic}. This may be because there aren't any recent developments, or the search terms need refinement. Try checking major news outlets directly for information about {topic}.",
            "source": "System Message",
            "published": datetime.now().isoformat(),
            "content": f"No recent articles were found about {topic}. This might be because there are no major recent developments on this topic, or because the search terms need to be more specific. You might try searching directly on major news websites for more information."
        }
        return [mock_article]
        
    except Exception as e:
        print(f"Error in search_with_optimized_query: {str(e)}")
        # Fall back to direct search
        print(f"Falling back to direct search for topic: {topic}")
        try:
            raw_articles = search_google_news(topic, 20)
            results = [article.to_dict() for article in raw_articles]
            if results:
                return results
        except:
            pass
            
        # If all fails, return a mock article
        mock_article = {
            "title": f"Information about {topic}",
            "link": f"https://en.wikipedia.org/wiki/{topic.replace(' ', '_')}",
            "snippet": f"We couldn't find recent news articles specifically about {topic}. This may be because there aren't any recent developments, or due to temporary search issues. Try checking major news outlets directly.",
            "source": "System Message",
            "published": datetime.now().isoformat(),
            "content": f"No recent articles were found about {topic}. This might be because there are no major recent developments on this topic, or because of temporary search issues. You might try searching directly on major news websites for more information."
        }
        return [mock_article]

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
        
        if not topic:
            raise HTTPException(status_code=400, detail="Topic is required")
        
        try:
            # First, use Claude to generate an optimized search query if available
            if claude_client:
                articles = search_with_optimized_query(topic)
            else:
                # Fallback to direct search if Claude is not available
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
        
        # The digest is now ready for the frontend
        
        result = {
            "status": "digest_generated",
            "topic": topic,
            "digest": digest,
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


@app.get("/api/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)