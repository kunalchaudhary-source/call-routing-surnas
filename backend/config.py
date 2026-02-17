"""Central configuration for the backend.

Loads environment variables (optionally from a .env file) and exposes
settings via `get_settings()`.
"""

from functools import lru_cache
from typing import Optional
import os
from pathlib import Path

from dotenv import load_dotenv


# Load variables from backend/.env (so .env placed inside the backend folder is picked up)
base_dir = Path(__file__).resolve().parent
load_dotenv(dotenv_path=base_dir / ".env")


class Settings:
    def __init__(self) -> None:
        # Required
        self.DATABASE_URL: str = os.getenv("DATABASE_URL")
        self.TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID")
        self.TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN")

        # Routing targets
        self.US_AGENT_POOL: str = os.getenv("US_AGENT_POOL", "+1US_AGENT_POOL")
        self.INDIA_AGENT_POOL: str = os.getenv("INDIA_AGENT_POOL", "+91INDIA_AGENT_POOL")

        # WebSocket URL for Twilio Media Streams → /ai-stream
        self.BACKEND_WS_URL: str = os.getenv("BACKEND_WS_URL", "wss://YOUR_BACKEND_URL/ai-stream")

        # Omni-dim (optional)
        self.OMNIDIM_API_KEY: Optional[str] = os.getenv("OMNIDIM_API_KEY")
        self.OMNIDIM_ENDPOINT: Optional[str] = os.getenv("OMNIDIM_ENDPOINT")
        self.OMNIDIM_STREAM_URL: Optional[str] = os.getenv("OMNIDIM_STREAM_URL")

        # Google Gemini (for AI responses)
        self.GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
        # Admin credentials for the admin console (optional - defaults provided)
        self.ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
        self.ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin@741")
        # TaskRouter (optional)
        self.TASKROUTER_WORKSPACE_SID: Optional[str] = os.getenv("TASKROUTER_WORKSPACE_SID")
        self.US_SUPPORT_QUEUE_SID: Optional[str] = os.getenv("US_SUPPORT_QUEUE_SID")
        self.INDIA_SUPPORT_QUEUE_SID: Optional[str] = os.getenv("INDIA_SUPPORT_QUEUE_SID")

        # Prefer this verified Twilio number for outbound Caller ID when set
        self.TWILIO_CALLER_ID: Optional[str] = os.getenv("TWILIO_CALLER_ID")

        # Basic validation
        if not self.DATABASE_URL:
            raise RuntimeError("DATABASE_URL environment variable is required")
        if not self.TWILIO_ACCOUNT_SID or not self.TWILIO_AUTH_TOKEN:
            raise RuntimeError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are required")
        # Comma-separated list of verified outbound numbers (useful for Twilio trial accounts)
        raw_verified = os.getenv("VERIFIED_OUTBOUND_NUMBERS", "")
        if raw_verified:
            self.VERIFIED_OUTBOUND_NUMBERS = [n.strip() for n in raw_verified.split(",") if n.strip()]
        else:
            self.VERIFIED_OUTBOUND_NUMBERS = []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
