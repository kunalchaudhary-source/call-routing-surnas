"""Main application entrypoint for the Call Routing Backend."""

import base64
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import Base, engine
from app.api import router as api_router
from app.services import config_service
import app.models.db_models  # noqa: F401

app = FastAPI(
    title="Call Routing Backend",
    description="Modular Telephony Routing Service supporting Twilio (US) and Plivo (India) with Cloud Run CRM Integration",
    version="2.0.0",
)

# Enable CORS for external widgets and browser clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def admin_auth_middleware(request: Request, call_next):
    """Protect /admin routes with Basic auth using configured settings, except /admin/login."""
    path = str(request.url.path)
    if request.method == "OPTIONS":
        return await call_next(request)

    if path.startswith("/admin") and not path.startswith("/admin/login"):
        auth = request.headers.get("authorization")
        if not auth or not auth.lower().startswith("basic "):
            return Response(status_code=401, content="Unauthorized")
        try:
            token = auth.split(" ", 1)[1]
            decoded = base64.b64decode(token).decode("utf-8")
            if ":" not in decoded:
                return Response(status_code=401, content="Unauthorized")
            username, password = decoded.split(":", 1)
            settings = get_settings()
            if username != settings.ADMIN_USERNAME or password != settings.ADMIN_PASSWORD:
                return Response(status_code=401, content="Unauthorized")
        except Exception:
            return Response(status_code=401, content="Unauthorized")

    return await call_next(request)


@app.on_event("startup")
def on_startup() -> None:
    """Initialize DB schema and load configuration cache on startup."""
    Base.metadata.create_all(bind=engine)
    config_service.initialize_config()


app.include_router(api_router)


@app.get("/")
async def root():
    return {"message": "Call Routing Backend is running", "version": "2.0.0"}
