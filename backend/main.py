"""Root entrypoint shim redirecting to the modular app package.

This guarantees backwards compatibility with existing startup commands:
    uvicorn backend.main:app --app-dir .. --port 8000 --reload
While also supporting the new standard:
    uvicorn app.main:app --port 8000 --reload
"""

import sys
from pathlib import Path

# Ensure backend directory is in sys.path when imported as backend.main
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.main import app

__all__ = ["app"]
