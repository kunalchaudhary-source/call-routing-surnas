"""Service for managing cached greetings, agents, prompts, and misheard word corrections."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.core.database import SessionLocal
from app.models.db_models import (
    Agent,
    AgentSpecialization,
    MisheardCorrection,
    VoiceGreeting,
    VoicePrompt,
    AppSetting,
)
from app.services.default_prompts import (
    DEFAULT_CORRECTIONS,
    DEFAULT_GREETINGS,
    DEFAULT_IVR_PROMPTS,
)
from app.core.logger import log_event

# Cache configuration
_cache: Dict[str, Any] = {
    "greetings": {},
    "ivr_prompts": {},
    "agents": [],
    "specializations": {},
    "corrections": {},
    "settings": {},
    "last_refresh": None,
}
CACHE_TTL_SECONDS = 300  # 5 minutes


def _is_cache_stale() -> bool:
    if _cache["last_refresh"] is None:
        return True
    return datetime.utcnow() - _cache["last_refresh"] > timedelta(seconds=CACHE_TTL_SECONDS)


def refresh_cache(force: bool = False) -> None:
    """Refresh all cached data from DB."""
    if not force and not _is_cache_stale():
        return

    db = SessionLocal()
    try:
        greetings = db.query(VoiceGreeting).all()
        _cache["greetings"] = {g.language: g.message for g in greetings}

        prompts = db.query(VoicePrompt).all()
        _cache["ivr_prompts"] = {p.key: p.message for p in prompts}

        agents = db.query(Agent).filter(Agent.is_active == True).all()
        _cache["agents"] = [
            {
                "id": a.id,
                "name": a.name,
                "phone_number": a.phone_number,
                "region": a.region,
                "is_default": a.is_default,
            }
            for a in agents
        ]

        specs = db.query(AgentSpecialization).all()
        spec_map: Dict[int, List[Dict[str, Any]]] = {}
        for s in specs:
            if s.agent_id not in spec_map:
                spec_map[s.agent_id] = []
            spec_map[s.agent_id].append({
                "category": s.category,
                "proficiency": s.proficiency_level,
            })
        _cache["specializations"] = spec_map

        corrections = db.query(MisheardCorrection).filter(MisheardCorrection.is_active == True).all()
        _cache["corrections"] = {c.wrong_word.lower(): c.correct_word.lower() for c in corrections}

        try:
            settings = db.query(AppSetting).all()
            _cache["settings"] = {s.key: s.value for s in settings}
        except Exception:
            _cache["settings"] = {}

        _cache["last_refresh"] = datetime.utcnow()
        log_event(None, "CONFIG_CACHE_REFRESHED", {
            "greetings": len(_cache["greetings"]),
            "agents": len(_cache["agents"]),
            "corrections": len(_cache["corrections"]),
        })
    except Exception as e:
        log_event(None, "CONFIG_CACHE_ERROR", {"error": str(e)})
    finally:
        db.close()


def get_voice_greeting(language_code: str) -> str:
    """Return IVR greeting for language, falling back to defaults."""
    refresh_cache()
    greetings = _cache["greetings"]
    if language_code in greetings:
        return greetings[language_code]
    return DEFAULT_GREETINGS.get(language_code, DEFAULT_GREETINGS.get("en-IN", "Welcome to Jadau."))


def get_ivr_prompt(key: str) -> str:
    """Return IVR prompt by key, falling back to defaults."""
    refresh_cache()
    prompts = _cache["ivr_prompts"]
    if key in prompts:
        return prompts[key]
    return DEFAULT_IVR_PROMPTS.get(key, "")


def correct_misheard_words(text: str) -> str:
    """Replace known misheard words with correct category terms."""
    if not text:
        return text
    refresh_cache()
    corrections = _cache["corrections"]
    words = text.lower().split()
    corrected = [corrections.get(w, w) for w in words]
    result = " ".join(corrected)
    for wrong, right in sorted(corrections.items(), key=lambda x: len(x[0]), reverse=True):
        if wrong in result:
            result = result.replace(wrong, right)
    return result


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Return runtime setting by key."""
    refresh_cache()
    return _cache["settings"].get(key, default)


def initialize_config() -> None:
    """Seed initial defaults in DB on startup if empty."""
    db = SessionLocal()
    try:
        # Seed greetings
        for lang, msg in DEFAULT_GREETINGS.items():
            if not db.query(VoiceGreeting).filter_by(language=lang).first():
                db.add(VoiceGreeting(language=lang, message=msg))

        # Seed prompts
        for key, msg in DEFAULT_IVR_PROMPTS.items():
            if not db.query(VoicePrompt).filter_by(key=key).first():
                db.add(VoicePrompt(key=key, message=msg))

        # Seed corrections
        for wrong, right in DEFAULT_CORRECTIONS.items():
            if not db.query(MisheardCorrection).filter_by(wrong_word=wrong).first():
                db.add(MisheardCorrection(wrong_word=wrong, correct_word=right))

        db.commit()
        refresh_cache(force=True)
    except Exception as exc:
        db.rollback()
        log_event(None, "CONFIG_INIT_ERROR", {"error": str(exc)})
    finally:
        db.close()
