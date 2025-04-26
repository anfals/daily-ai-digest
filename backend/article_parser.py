import requests
from bs4 import BeautifulSoup
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional
import re
from datetime import datetime

class ArticleParser:
    """
    Class for fetching and parsing article content from URLs
    """
    
    @staticmethod
    def fetch_article_content(url: str, timeout: int = 10) -> Optional[str]:
        """
        Fetches and extracts the main content from an article URL
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
            }
            
            response = requests.get(url, headers=headers, timeout=timeout)
            
            if response.status_code != 200:
                print(f"Error fetching article {url}: Status code {response.status_code}")
                return None
                
            # Parse the HTML content
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script, style elements and comments
            for element in soup(['script', 'style', 'header', 'footer', 'nav', 'aside']):
                element.decompose()
            
            # For demo purposes, we use a simplified extraction approach
            # In a production environment, you would use more sophisticated methods
            
            # Try to find article content in common containers
            article_selectors = [
                'article', '.article', '.post', '.content', '.post-content',
                '[itemprop="articleBody"]', '.story', '.entry-content', 
                '.page-content', '.main-content', 'main'
            ]
            
            content = None
            
            # Try each selector until we find content
            for selector in article_selectors:
                article_element = soup.select_one(selector)
                if article_element and len(article_element.get_text(strip=True)) > 200:
                    content = article_element
                    break
            
            # If we still haven't found the content, use the body as fallback
            if not content:
                content = soup.body
                
            if not content:
                return f"Could not extract content from {url}"
                
            # Get the text content, ignoring boilerplate elements
            text = content.get_text(separator='\n')
            
            # Clean up the text
            text = re.sub(r'\n+', '\n', text)      # Remove extra newlines
            text = re.sub(r'\s+', ' ', text)       # Collapse whitespace
            text = re.sub(r'\n', ' ', text)        # Replace newlines with spaces
            
            # Trim the text to a reasonable length (10,000 characters max)
            if len(text) > 10000:
                text = text[:10000] + "... [content truncated]"
                
            return text
            
        except Exception as e:
            print(f"Error processing article {url}: {str(e)}")
            return f"Error processing article: {str(e)}"

    @staticmethod
    def fetch_multiple_articles(articles: List[Dict[str, Any]], max_workers: int = 5) -> List[Dict[str, Any]]:
        """
        Fetches content for multiple articles in parallel
        """
        articles_with_content = []
        
        def fetch_and_add_content(article):
            try:
                # Check if article has a valid URL
                if "link" not in article or not article["link"]:
                    article["content"] = "No URL available for this article"
                    return article
                
                # Skip invalid URLs
                if not article["link"] or "example.com" in article["link"]:
                    # For invalid URLs, use the snippet as content
                    article["content"] = f"{article.get('title', 'No title')}. {article.get('snippet', '')}"
                    return article
                
                # Ensure article has a properly formatted published timestamp
                if "published" not in article or not article["published"]:
                    article["published"] = datetime.now().isoformat() + "Z"
                else:
                    # Normalize the date format if needed
                    try:
                        pub_date = article["published"]
                        # Check if it has timezone information
                        if "Z" not in pub_date and "+" not in pub_date and "-" not in pub_date[-6:]:
                            # Add Z if no timezone
                            article["published"] = pub_date + "Z"
                        elif "+" in pub_date and "T" not in pub_date:
                            # This might be a formatted date with timezone like "Apr 3, 2025+06:00"
                            # Try to convert to ISO format
                            try:
                                # This is a simplistic approach - a more robust solution would
                                # use a dedicated date parsing library for the various formats
                                article["published"] = datetime.now().isoformat() + "Z"
                            except:
                                # If parsing fails, just use current time
                                article["published"] = datetime.now().isoformat() + "Z"
                    except Exception as e:
                        print(f"Error normalizing date format: {e}")
                        # Default to current time if issues arise
                        article["published"] = datetime.now().isoformat() + "Z"
                
                # Fetch the content
                content = ArticleParser.fetch_article_content(article["link"])
                
                # Add the content to the article
                article["content"] = content if content else "Could not extract content"
                return article
                
            except Exception as e:
                print(f"Error in fetch_and_add_content: {str(e)}")
                article["content"] = f"Error fetching content: {str(e)}"
                return article
        
        # Use ThreadPoolExecutor to fetch content in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            articles_with_content = list(executor.map(fetch_and_add_content, articles))
            
        return articles_with_content