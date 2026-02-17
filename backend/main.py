from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import base64

from backend.config import get_settings

from backend.routes import router as routes_router
from backend.routes.admin import router as admin_router
from backend.db import Base, engine


app = FastAPI(title="Call Routing Backend")


# Enable CORS so Omni-dim and other services can preflight (OPTIONS) and POST
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def admin_auth_middleware(request: Request, call_next):
    """Protect /admin routes with simple Basic auth using env vars, except /admin/login."""
    path = str(request.url.path)
    # Allow CORS preflight requests through without auth
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
    """Create database tables and initialize config on startup."""
    # Import models so that SQLAlchemy is aware of them
    from backend.models import db_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    
    # Initialize configurable prompts, agents, and corrections
    from backend.services import config_service
    config_service.initialize_config()


# Include package-level router that aggregates all route modules
app.include_router(routes_router)
app.include_router(admin_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
