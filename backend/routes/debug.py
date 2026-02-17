from fastapi import APIRouter, Query
from backend.services import gemini_service

router = APIRouter()


@router.get("/debug/gemini")
async def debug_gemini(text: str = Query(..., description="Text to run moderation on")):
    """Debug endpoint to test Gemini moderation behavior for a given text."""
    res = gemini_service.debug_moderation(text)
    return res
