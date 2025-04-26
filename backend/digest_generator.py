from typing import Dict, List, Any, Optional
import anthropic
import time
import json
import os
from datetime import datetime

class DigestGenerator:
    """
    Class for generating article digests using Claude
    """
    
    def __init__(self, claude_client):
        self.claude_client = claude_client
        
    def generate_digest(self, topic: str, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate a digest for a collection of articles using Claude
        
        Returns a dictionary with:
        - digest_text: The formatted digest text
        - selected_articles: The articles selected as most relevant
        - summary: A short summary of the key points
        """
        
        if not self.claude_client:
            return self._generate_mock_digest(topic, articles)
            
        try:
            # Prepare the articles data for Claude
            articles_data = []
            for i, article in enumerate(articles, 1):
                article_info = {
                    "id": i,
                    "title": article.get("title", "No title"),
                    "source": article.get("source", "Unknown source"),
                    "url": article.get("link", ""),
                    "snippet": article.get("snippet", ""),
                    "content": article.get("content", "No content available")[:5000]  # Limit content length
                }
                articles_data.append(article_info)
                
            # Construct the prompt for Claude
            prompt = self._construct_prompt(topic, articles_data)
            
            # Call Claude API to generate the digest
            response = self.claude_client.messages.create(
                model="claude-3-7-sonnet-20250219",
                max_tokens=4000,
                temperature=0.3,
                system="""You are a professional news digest writer. Your task is to analyze articles, 
                identify the most relevant ones for the given topic, and create a concise, informative 
                digest that captures the essential information.

                IMPORTANT RULES:
                1. Only select articles in English
                2. Provide a 2-3 line detailed summary for each article that captures the key information
                3. Focus on the most important, timely, and relevant articles
                4. Ensure your article digests are informative enough that someone could understand the main points without reading the full article
                5. Check the article publication dates and prefer more recent articles when relevant""",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract the response text
            result = response.content[0].text
            
            # Parse the structured output
            digest_data = self._parse_claude_response(result)
            
            # Add the raw text as well
            digest_data["raw_claude_response"] = result
            
            return digest_data
            
        except Exception as e:
            print(f"Error generating digest with Claude: {str(e)}")
            # Fall back to mock digest if Claude fails
            return self._generate_mock_digest(topic, articles)
    
    def _construct_prompt(self, topic: str, articles: List[Dict[str, Any]]) -> str:
        """Create a prompt for Claude to generate a structured summary with article highlights"""
        
        prompt = f"""# Task: Create a Structured News Summary on "{topic}"

I'm providing you with {len(articles)} news articles related to {topic}.

## Your Tasks:
1. Identify which articles are most relevant to the topic "{topic}"
2. Select up to 5 most relevant, recent and informative articles in English
3. Create a structured summary with:
   - An overall summary explaining the latest news on this topic
   - A list of the top articles with detailed individual summaries and links
4. Format your response as structured data that I can parse

## Articles:
"""

        for article in articles:
            # Include publication date in the prompt if available
            pub_date = ""
            if 'published' in article and article['published']:
                pub_date = f"Published: {article['published']}"
                
            prompt += f"""
----- Article {article['id']} -----
Title: {article['title']}
Source: {article['source']}
URL: {article['url']}
{pub_date}
Snippet: {article['snippet']}

Content:
{article['content']}

----------------------
"""

        prompt += """
## Response Format:
Provide your response in the following structured format:

<selected_articles>
List the IDs of the relevant articles you selected, in order of relevance.
Example: [3, 7, 2, 9, 1]
</selected_articles>

<overall_summary>
A 3-4 sentence high-level summary explaining the latest news on this topic, synthesizing the information from all selected articles.
</overall_summary>

<article_highlights>
For each of the selected articles, provide:
1. The article title
2. The source
3. The URL
4. A 4-5 sentence detailed summary of the article's key points that captures the most important information

Do not include any "Key Insight" section.
Format this as a numbered list with clear headings for each article.
</article_highlights>
"""

        return prompt
        
    def _parse_claude_response(self, response: str) -> Dict[str, Any]:
        """Parse Claude's response into structured data"""
        result = {
            "selected_articles": [],
            "overall_summary": "",
            "article_highlights": ""
        }
        
        # Extract sections using regex
        import re
        
        # Get selected articles
        selected_articles_match = re.search(r'<selected_articles>(.*?)</selected_articles>', response, re.DOTALL)
        if selected_articles_match:
            try:
                # Try to parse as JSON array first
                selected_text = selected_articles_match.group(1).strip()
                if '[' in selected_text and ']' in selected_text:
                    # Extract the array part
                    array_part = selected_text[selected_text.find('['):selected_text.rfind(']')+1]
                    result["selected_articles"] = json.loads(array_part)
                else:
                    # Fall back to parsing as comma-separated list
                    result["selected_articles"] = [int(x.strip()) for x in selected_text.split(',') if x.strip().isdigit()]
            except:
                # If parsing fails, leave as empty list
                pass
                
        # Get overall summary
        summary_match = re.search(r'<overall_summary>(.*?)</overall_summary>', response, re.DOTALL)
        if summary_match:
            result["overall_summary"] = summary_match.group(1).strip()
            
        # Get article highlights
        highlights_match = re.search(r'<article_highlights>(.*?)</article_highlights>', response, re.DOTALL)
        if highlights_match:
            result["article_highlights"] = highlights_match.group(1).strip()
            
        # Store the raw response for debugging
        result["raw_response"] = response
            
        return result
        
    def _generate_mock_digest(self, topic: str, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate a mock summary and highlights when Claude is unavailable"""
        
        # Select the first 5 articles (or fewer if there aren't 5)
        selected_articles = list(range(1, min(6, len(articles) + 1)))
        
        # Create the current date
        current_date = datetime.now().strftime("%B %d, %Y")
        
        # Generate the overall summary
        overall_summary = (
            f"As of {current_date}, the latest news on {topic} indicates significant developments "
            f"across several areas. Recent reports from {', '.join([a.get('source', 'various sources') for a in articles[:3] if a.get('source')])} "
            f"highlight important trends and updates that are shaping this field. "
            f"The most relevant information comes from articles covering different aspects of {topic}, "
            f"providing a comprehensive overview of the current situation."
        )
        
        # Generate article highlights
        article_highlights = f"# Top Articles on {topic.upper()}\n\n"
        
        for i, article_id in enumerate(selected_articles):
            if article_id <= len(articles):
                article = articles[article_id - 1]  # article_id is 1-indexed
                title = article.get("title", f"Article {article_id}")
                source = article.get("source", "Unknown source")
                url = article.get("url", article.get("link", "#"))
                snippet = article.get("snippet", "No preview available")
                
                article_highlights += f"## {i+1}. {title}\n\n"
                article_highlights += f"**Source:** {source}\n\n"
                
                # Always add published time - use the original ISO format for the frontend to format
                if article.get("published"):
                    try:
                        # Add the raw ISO date string - frontend will format it as "time ago"
                        pub_date_iso = article["published"]
                        
                        # Normalize the date format to a clean ISO format
                        try:
                            # Try to parse the date to ensure proper formatting
                            if "+" in pub_date_iso or " " in pub_date_iso:
                                # This might be something like "Apr 3, 2025+06:00" or non-standard format
                                # Try to convert to a standard date
                                parsed_date = datetime.fromisoformat(pub_date_iso.replace("Z", "+00:00"))
                                pub_date_iso = parsed_date.isoformat() + "Z"
                            elif "Z" not in pub_date_iso and "+" not in pub_date_iso:
                                # Add timezone if missing
                                pub_date_iso += "Z"
                        except:
                            # If parsing fails, leave as is - frontend will handle it
                            pass
                            
                        article_highlights += f"**Published:** {pub_date_iso}\n\n"
                    except Exception as e:
                        print(f"Error formatting publication time: {e}")
                        # If error, use current time as fallback
                        now_iso = datetime.now().isoformat() + "Z"
                        article_highlights += f"**Published:** {now_iso}\n\n"
                else:
                    # If no publication date, use current time
                    now_iso = datetime.now().isoformat() + "Z"
                    article_highlights += f"**Published:** {now_iso}\n\n"
                
                article_highlights += f"**URL:** [{url}]({url})\n\n"
                article_highlights += f"**Summary:** {snippet}\n\n"
                
                if i < len(selected_articles) - 1:
                    article_highlights += "---\n\n"
                      
        return {
            "selected_articles": selected_articles,
            "overall_summary": overall_summary,
            "article_highlights": article_highlights,
            "is_mock": True
        }