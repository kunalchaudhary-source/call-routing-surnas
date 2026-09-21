"""Central configuration for the application.

Loads environment variables from `.env` and exposes settings via `get_settings()`.
"""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional
import os

from dotenv import load_dotenv

# Search for .env in backend directory first, then current working directory
backend_dir = Path(__file__).resolve().parent.parent.parent
env_candidates = [
    backend_dir / ".env",
    Path.cwd() / ".env",
    Path.cwd() / "backend" / ".env",
]
for env_file in env_candidates:
    if env_file.is_file():
        load_dotenv(dotenv_path=env_file)
        break


class Settings:
    def __init__(self) -> None:
        # Database
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "")
        if not self.DATABASE_URL:
            raise RuntimeError("DATABASE_URL environment variable is required")

        # Telephony - Twilio (US)
        self.TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.TWILIO_CALLER_ID: Optional[str] = os.getenv("TWILIO_CALLER_ID")
        raw_verified = os.getenv("VERIFIED_OUTBOUND_NUMBERS", "")
        self.VERIFIED_OUTBOUND_NUMBERS: List[str] = (
            [n.strip() for n in raw_verified.split(",") if n.strip()]
            if raw_verified
            else []
        )

        # Telephony - Plivo (India)
        self.PLIVO_AUTH_ID: Optional[str] = os.getenv("PLIVO_AUTH_ID")
        self.PLIVO_AUTH_TOKEN: Optional[str] = os.getenv("PLIVO_AUTH_TOKEN")
        self.PLIVO_PHONE_NUMBER: Optional[str] = os.getenv("PLIVO_PHONE_NUMBER")

        # CRM - Surana Cloud Run Microservice
        self.SURANA_CRM_URL: str = os.getenv(
            "SURANA_CRM_URL",
            "https://surana-duvi-ceronica-lead-491046241370.asia-south2.run.app",
        )
        self.SURANA_INGEST_SECRET: Optional[str] = os.getenv("SURANA_INGEST_SECRET")
        self.SURANA_WORKER_SECRET: Optional[str] = os.getenv("SURANA_WORKER_SECRET")

        # Agent Routing Pools & Dial Timeout
        self.US_AGENT_POOL: str = os.getenv("US_AGENT_POOL", "+1US_AGENT_POOL")
        self.INDIA_AGENT_POOL: str = os.getenv("INDIA_AGENT_POOL", "+91INDIA_AGENT_POOL")
        self.AGENT_DIAL_TIMEOUT: int = int(os.getenv("AGENT_DIAL_TIMEOUT", "120"))

        # AI & External integrations
        self.GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
        self.BACKEND_WS_URL: str = os.getenv("BACKEND_WS_URL", "wss://YOUR_BACKEND_URL/ai-stream")
        self.OMNIDIM_API_KEY: Optional[str] = os.getenv("OMNIDIM_API_KEY")
        self.OMNIDIM_ENDPOINT: Optional[str] = os.getenv("OMNIDIM_ENDPOINT")
        self.OMNIDIM_STREAM_URL: Optional[str] = os.getenv("OMNIDIM_STREAM_URL")

        # Admin Auth
        self.ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
        self.ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin@741")

        # TaskRouter (optional)
        self.TASKROUTER_WORKSPACE_SID: Optional[str] = os.getenv("TASKROUTER_WORKSPACE_SID")
        self.US_SUPPORT_QUEUE_SID: Optional[str] = os.getenv("US_SUPPORT_QUEUE_SID")
        self.INDIA_SUPPORT_QUEUE_SID: Optional[str] = os.getenv("INDIA_SUPPORT_QUEUE_SID")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
