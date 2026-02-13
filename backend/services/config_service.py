"""Service for managing cached greetings, agents, and corrections."""

from datetime import datetime, timedelta
from typing import Optional

from backend.db import SessionLocal
from backend.models.db_models import Agent, AgentSpecialization, MisheardCorrection, VoiceGreeting, VoicePrompt
from backend.services.default_prompts import DEFAULT_GREETINGS, DEFAULT_IVR_PROMPTS
from backend.services.logger import log_event


# Cache configuration
_cache = {
    "greetings": {},
    "ivr_prompts": {},
    "agents": [],
    "specializations": {},
    "corrections": {},
    "last_refresh": None,
}
CACHE_TTL_SECONDS = 300  # 5 minutes


def _is_cache_stale() -> bool:
    """Check if cache needs refresh."""
    if _cache["last_refresh"] is None:
        return True
    return datetime.utcnow() - _cache["last_refresh"] > timedelta(seconds=CACHE_TTL_SECONDS)


def refresh_cache(force: bool = False) -> None:
    """Refresh all cached data from DB."""
    if not force and not _is_cache_stale():
        return
    
    db = SessionLocal()
    try:
        # Load greetings
        greetings = db.query(VoiceGreeting).all()
        _cache["greetings"] = {g.language: g.message for g in greetings}

        # Load IVR prompts
        prompts = db.query(VoicePrompt).all()
        _cache["ivr_prompts"] = {p.key: p.message for p in prompts}
        
        # Load agents
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
        
        # Load specializations (grouped by agent_id)
        specs = db.query(AgentSpecialization).all()
        spec_map = {}
        for s in specs:
            if s.agent_id not in spec_map:
                spec_map[s.agent_id] = []
            spec_map[s.agent_id].append({
                "category": s.category,
                "proficiency": s.proficiency_level,
            })
        _cache["specializations"] = spec_map
        
        # Load misheard corrections
        corrections = db.query(MisheardCorrection).filter(MisheardCorrection.is_active == True).all()
        _cache["corrections"] = {c.wrong_word.lower(): c.correct_word.lower() for c in corrections}
        
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
    """Return the IVR greeting for a language, falling back to defaults."""
    refresh_cache()
    greetings = _cache["greetings"]
    if language_code in greetings:
        return greetings[language_code]
    return DEFAULT_GREETINGS.get(language_code, DEFAULT_GREETINGS["en-IN"])


def get_all_voice_greetings() -> dict[str, str]:
    """Return all configured greetings keyed by language."""
    refresh_cache()
    return _cache["greetings"]


def get_ivr_prompt(key: str) -> str:
    """Return the IVR prompt text for a given key, falling back to defaults."""
    refresh_cache()
    prompts = _cache["ivr_prompts"]
    if key in prompts:
        return prompts[key]
    return DEFAULT_IVR_PROMPTS.get(key, "")


def get_all_ivr_prompts() -> dict[str, str]:
    """Return all configured IVR prompts keyed by prompt key."""
    refresh_cache()
    # Merge defaults with overrides so admin UI always sees all keys
    merged = {**DEFAULT_IVR_PROMPTS}
    merged.update(_cache["ivr_prompts"])
    return merged


def get_misheard_corrections() -> dict[str, str]:
    """Get all misheard word corrections."""
    refresh_cache()
    return _cache["corrections"]


def correct_misheard_words(text: str) -> str:
    """Apply misheard word corrections to text."""
    corrections = get_misheard_corrections()
    if not corrections:
        return text

    result = text.lower()
    for wrong, correct in corrections.items():
        if wrong in result:
            result = result.replace(wrong, correct)
    return result


def get_agent_for_category_and_region(category: Optional[str], region: str) -> Optional[dict]:
    """Find the best agent for a category and region.
    
    Priority:
    1. Specialist in category + matching region (highest proficiency)
    2. Specialist in category + GLOBAL region
    3. Default agent for region
    4. Any active agent for region
    
    Args:
        category: Jewelry category (e.g., 'necklace', 'polki') or None for general
        region: 'US' or 'IN'
    
    Returns:
        Agent dict with id, name, phone_number, region, specializations
    """
    refresh_cache()
    agents = _cache["agents"]
    specs = _cache["specializations"]
    
    if not agents:
        return None
    
    # Build agent lookup with their specializations
    agents_with_specs = []
    for agent in agents:
        agent_specs = specs.get(agent["id"], [])
        agents_with_specs.append({
            **agent,
            "specializations": agent_specs,
            "categories": [s["category"] for s in agent_specs],
        })
    
    # If category specified, find specialist
    if category:
        # Priority 1: Specialist in region
        regional_specialists = [
            a for a in agents_with_specs
            if a["region"] == region and category in a["categories"]
        ]
        if regional_specialists:
            # Return highest proficiency
            best = max(regional_specialists, key=lambda a: max(
                (s["proficiency"] for s in a["specializations"] if s["category"] == category),
                default=0
            ))
            return best
        
        # Priority 2: Global specialist
        global_specialists = [
            a for a in agents_with_specs
            if a["region"] == "GLOBAL" and category in a["categories"]
        ]
        if global_specialists:
            best = max(global_specialists, key=lambda a: max(
                (s["proficiency"] for s in a["specializations"] if s["category"] == category),
                default=0
            ))
            return best
    
    # Priority 3: Default agent for region
    defaults = [a for a in agents_with_specs if a["region"] == region and a["is_default"]]
    if defaults:
        return defaults[0]
    
    # Priority 4: Any agent in region
    regional = [a for a in agents_with_specs if a["region"] == region]
    if regional:
        return regional[0]
    
    # Priority 5: Global default
    global_defaults = [a for a in agents_with_specs if a["region"] == "GLOBAL" and a["is_default"]]
    if global_defaults:
        return global_defaults[0]
    
    # Last resort: any agent
    return agents_with_specs[0] if agents_with_specs else None


def get_agent_phone_for_region(region: str) -> Optional[str]:
    """Get default agent phone number for a region (backward compatible)."""
    agent = get_agent_for_category_and_region(None, region)
    return agent["phone_number"] if agent else None


# ==================== DB POPULATION HELPERS ====================

def seed_default_corrections() -> None:
    """Seed default misheard word corrections if DB is empty."""
    db = SessionLocal()
    try:
        existing = db.query(MisheardCorrection).count()
        if existing > 0:
            return
        
        from backend.services.default_prompts import DEFAULT_CORRECTIONS
        
        for wrong, correct in DEFAULT_CORRECTIONS.items():
            correction = MisheardCorrection(
                wrong_word=wrong,
                correct_word=correct,
                is_active=True,
            )
            db.add(correction)
        
        db.commit()
        log_event(None, "CORRECTIONS_SEEDED", {"count": len(DEFAULT_CORRECTIONS)})
    except Exception as e:
        log_event(None, "CORRECTIONS_SEED_ERROR", {"error": str(e)})
        db.rollback()
    finally:
        db.close()


def seed_default_greetings() -> None:
    """Seed default voice greetings if DB is empty."""
    db = SessionLocal()
    try:
        existing = db.query(VoiceGreeting).count()
        if existing > 0:
            return

        for language, message in DEFAULT_GREETINGS.items():
            greeting = VoiceGreeting(language=language, message=message)
            db.add(greeting)

        db.commit()
        log_event(None, "GREETINGS_SEEDED", {"count": len(DEFAULT_GREETINGS)})
    except Exception as e:
        log_event(None, "GREETINGS_SEED_ERROR", {"error": str(e)})
        db.rollback()
    finally:
        db.close()


def seed_default_ivr_prompts() -> None:
    """Seed default IVR prompts if DB is empty."""
    db = SessionLocal()
    try:
        existing = db.query(VoicePrompt).count()
        if existing > 0:
            return

        for key, message in DEFAULT_IVR_PROMPTS.items():
            prompt = VoicePrompt(key=key, message=message)
            db.add(prompt)

        db.commit()
        log_event(None, "IVR_PROMPTS_SEEDED", {"count": len(DEFAULT_IVR_PROMPTS)})
    except Exception as e:
        log_event(None, "IVR_PROMPTS_SEED_ERROR", {"error": str(e)})
        db.rollback()
    finally:
        db.close()


def seed_default_agents() -> None:
    """Seed default agents if DB is empty."""
    db = SessionLocal()
    try:
        existing = db.query(Agent).count()
        if existing > 0:
            return
        # Do NOT seed placeholder agents from environment variables.
        # Operators must configure agents in the database explicitly.
        log_event(None, "NO_AGENTS_CONFIGURED_IN_DB", {"message": "No agents found in DB. Please configure agents in the database."})
    except Exception as e:
        log_event(None, "AGENTS_SEED_ERROR", {"error": str(e)})
        db.rollback()
    finally:
        db.close()


def initialize_config() -> None:
    """Initialize all default config on startup."""
    seed_default_corrections()
    seed_default_agents()
    seed_default_greetings()
    refresh_cache(force=True)
