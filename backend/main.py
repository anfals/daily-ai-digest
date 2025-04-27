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

def generate_search_queries(topic: str) -> List[str]:
    """
    Uses Claude to generate optimized search queries for a given topic.
    Returns a list of 5 search queries designed to find diverse, recent, and relevant articles.
    """
    # If Claude client is not available, use default queries
    if not claude_client:
        print("Claude client not available, using default queries")
        return [f"{topic} latest news", f"{topic} recent events", f"{topic} today", f"{topic} updates", f"{topic} current"]
    
    try:
        # Create a prompt for Claude to generate diverse search queries
        prompt = f"""# Task: Generate Optimized News Search Queries

I need to find the most relevant and recent news articles about "{topic}".

Please generate 5 specific search queries that would help me find:
1. The latest breaking news on this topic
2. The most trending or popular coverage
3. In-depth analyses or comprehensive coverage
4. Different perspectives or angles on the topic
5. Specific developments or key aspects of the topic

Your queries should:
- Be specific and targeted to yield high-quality news results
- Focus on articles from the past 24 hours for maximum freshness
- Be optimized for news search engines
- Include relevant keywords, names, events, or specifications related to {topic}
- Enable finding diverse information covering different aspects of the topic
- Each query should target a different aspect to avoid duplicate coverage
- Aim to find English-language content
- DO NOT include phrases like "last 24 hours" or "recent" in the queries themselves, as these don't work well with search engines
- Make queries direct and simple, focusing on the subject matter itself

Format your response as a numbered list of 5 queries, one per line.
"""

        # Call Claude API to generate queries
        response = claude_client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1000,
            temperature=0.3,
            system="You are a professional search query optimizer specializing in finding recent, relevant news articles.",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # Extract the response text
        result = response.content[0].text
        
        # Parse the queries from the response
        queries = []
        lines = result.strip().split('\n')
        for line in lines:
            # Match numbered lines (e.g. "1. " or "1) ")
            if re.match(r'^\d+[\.\)]\s+', line):
                # Extract the query part (after the number and space)
                query = re.sub(r'^\d+[\.\)]\s+', '', line).strip()
                if query:
                    queries.append(query)
        
        # Ensure we have at most 5 queries
        if not queries:
            print("Failed to parse any queries from Claude's response, using default queries")
            return [f"{topic} latest news", f"{topic} analysis", f"{topic} developments", f"{topic} trends", f"{topic} impact"]
            
        print(f"Generated {len(queries)} search queries for topic '{topic}': {queries}")
        return queries[:5]
        
    except Exception as e:
        print(f"Error generating search queries with Claude: {str(e)}")
        # Return default queries if Claude fails
        return [f"{topic} latest news", f"{topic} analysis", f"{topic} developments", f"{topic} trends", f"{topic} impact"]

def search_with_optimized_queries(topic: str) -> List[Dict[str, Any]]:
    """
    Uses Claude to generate optimized search queries, then executes each query
    to gather articles, and returns the collected articles.
    """
    try:
        # Generate optimized queries using Claude
        print(f"Generating optimized search queries for topic: {topic}")
        queries = generate_search_queries(topic)
        print(f"Generated {len(queries)} optimized queries for topic '{topic}': {queries}")
        
        # Execute each query and collect results
        all_articles = []
        seen_urls = set()  # Track URLs to avoid duplicates
        
        # First attempt with optimized queries
        for query in queries:
            print(f"Executing query: {query}")
            # Get up to 5 articles per query
            results = search_google_news(query, 5)
            
            if results:
                for article in results:
                    # Avoid adding duplicate articles
                    if article.link not in seen_urls:
                        seen_urls.add(article.link)
                        all_articles.append(article.to_dict())
                        
                print(f"Found {len(results)} articles for query: {query}")
            else:
                print(f"No results found for query: {query}")
                
        print(f"Total unique articles collected from optimized queries: {len(all_articles)}")
        
        # If we didn't find any articles with optimized queries, try direct search
        if not all_articles:
            print(f"No articles found with optimized queries, trying direct search")
            # Try alternate search strategies if we got no results
            direct_query = f"{topic}"
            print(f"Trying direct query: {direct_query}")
            direct_results = search_google_news(direct_query, 10)
            
            if direct_results:
                for article in direct_results:
                    if article.link not in seen_urls:
                        seen_urls.add(article.link)
                        all_articles.append(article.to_dict())
            
            # If still no results, try with "news" added explicitly
            if not all_articles:
                news_query = f"{topic} news"
                print(f"Trying news query: {news_query}")
                news_results = search_google_news(news_query, 10)
                
                if news_results:
                    for article in news_results:
                        if article.link not in seen_urls:
                            seen_urls.add(article.link)
                            all_articles.append(article.to_dict())
        
        print(f"Final total unique articles collected: {len(all_articles)}")
        
        # If still no articles, create a mock article with information
        if not all_articles:
            print(f"No articles found for {topic} after all search attempts. Creating a mock article.")
            mock_article = {
                "title": f"Information about {topic}",
                "link": f"https://en.wikipedia.org/wiki/{topic.replace(' ', '_')}",
                "snippet": f"We couldn't find recent news articles specifically about {topic}. This may be because there aren't any recent developments, or the search terms need refinement. Try checking major news outlets directly for information about {topic}.",
                "source": "System Message",
                "published": datetime.now().isoformat(),
                "content": f"No recent articles were found about {topic}. This might be because there are no major recent developments on this topic, or because the search terms need to be more specific. You might try searching directly on major news websites for more information."
            }
            all_articles = [mock_article]
        
        return all_articles
        
    except Exception as e:
        print(f"Error in search_with_optimized_queries: {str(e)}")
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
        phone_number = req.phone_number
        
        if not topic or not phone_number:
            raise HTTPException(status_code=400, detail="Topic and phone number are required")
        
        try:
            # First, use Claude to generate optimized search queries if available
            if claude_client:
                articles = search_with_optimized_queries(topic)
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


@app.get("/api/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)