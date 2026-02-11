from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
