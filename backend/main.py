from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

# TODO: Add your Anthropic API key and endpoint here
ANTHROPIC_API_KEY = "your-anthropic-api-key"
# TODO: Add your Twilio credentials here
TWILIO_ACCOUNT_SID = "your-twilio-sid"
TWILIO_AUTH_TOKEN = "your-twilio-auth-token"
TWILIO_PHONE_NUMBER = "your-twilio-phone-number"


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

@app.post("/api/digest")
async def create_digest(req: DigestRequest):
    # 1. TODO: Validate phone number format
    topic = req.topic
    phone_number = req.phone_number

    # 2. TODO: Call Anthropic API to generate search queries (agentic reasoning)
    # Example: search_queries = call_anthropic_agent(topic)
    search_queries = [f"latest news about {topic}"]  # Placeholder

    # 3. TODO: Execute web searches and scrape results
    # Example: articles = scrape_news(search_queries)
    articles = [
        {"title": "Sample News 1", "content": "Sample content 1."},
        {"title": "Sample News 2", "content": "Sample content 2."}
    ]  # Placeholder

    # 4. TODO: Call Anthropic API to synthesize digest from articles
    # Example: digest = call_anthropic_summarizer(articles)
    digest = f"Daily digest for {topic}: ..."  # Placeholder

    # 5. TODO: Send SMS via Twilio
    # Example: send_sms(phone_number, digest)
    sms_status = "sent (placeholder)"

    return {
        "status": "digest_sent",
        "topic": topic,
        "phone_number": phone_number,
        "digest": digest,
        "sms_status": sms_status
    }

@app.get("/api/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
