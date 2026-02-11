"""Admin API routes for managing greetings, agents, and corrections."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.db import SessionLocal
from backend.models.db_models import Agent, AgentSpecialization, MisheardCorrection, VoiceGreeting, VoicePrompt
from backend.services import config_service
from backend.services.default_prompts import DEFAULT_GREETINGS, DEFAULT_IVR_PROMPTS
from backend.services.logger import log_event


router = APIRouter(prefix="/admin", tags=["admin"])


# ==================== PYDANTIC MODELS ====================

class AgentCreate(BaseModel):
    name: str
    phone_number: str
    region: str  # 'US', 'IN', 'GLOBAL'
    is_default: bool = False
    specializations: list[str] = []  # e.g., ['necklace', 'polki']


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    region: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class SpecializationAdd(BaseModel):
    category: str
    proficiency_level: int = 1  # 1=basic, 2=intermediate, 3=expert


class CorrectionCreate(BaseModel):
    wrong_word: str
    correct_word: str


class GreetingUpdate(BaseModel):
    message: str


class IVRPromptUpdate(BaseModel):
    message: str


# ==================== GREETING ENDPOINTS ====================

@router.get("/greetings")
async def list_greetings():
    """List all configured voice greetings."""
    db = SessionLocal()
    try:
        greetings = db.query(VoiceGreeting).order_by(VoiceGreeting.language).all()
        overrides = {g.language: g for g in greetings}

        response = []
        for language, default_message in DEFAULT_GREETINGS.items():
            record = overrides.pop(language, None)
            response.append({
                "id": record.id if record else None,
                "language": language,
                "message": record.message if record else default_message,
                "updated_at": record.updated_at if record else None,
                "is_override": record is not None,
            })

        for remaining in sorted(overrides.values(), key=lambda g: g.language):
            response.append({
                "id": remaining.id,
                "language": remaining.language,
                "message": remaining.message,
                "updated_at": remaining.updated_at,
                "is_override": True,
            })

        return response
    finally:
        db.close()


# ==================== IVR PROMPT ENDPOINTS ====================

@router.get("/ivr-prompts")
async def list_ivr_prompts():
    """List all IVR prompt texts (menu, reprompt, confirmation, invalid)."""
    db = SessionLocal()
    try:
        prompts = db.query(VoicePrompt).order_by(VoicePrompt.key).all()
        overrides = {p.key: p for p in prompts}

        response = []
        for key, default_message in DEFAULT_IVR_PROMPTS.items():
            record = overrides.pop(key, None)
            response.append({
                "id": record.id if record else None,
                "key": key,
                "message": record.message if record else default_message,
                "updated_at": record.updated_at if record else None,
                "is_override": record is not None,
            })

        for remaining in sorted(overrides.values(), key=lambda p: p.key):
            response.append({
                "id": remaining.id,
                "key": remaining.key,
                "message": remaining.message,
                "updated_at": remaining.updated_at,
                "is_override": True,
            })

        return response
    finally:
        db.close()


@router.get("/ivr-prompts/{key}")
async def get_ivr_prompt_record(key: str):
    """Fetch a specific IVR prompt by key (menu, reprompt, confirmation, invalid)."""
    db = SessionLocal()
    try:
        prompt = db.query(VoicePrompt).filter(VoicePrompt.key == key).first()
        if prompt:
            return {
                "id": prompt.id,
                "key": prompt.key,
                "message": prompt.message,
                "updated_at": prompt.updated_at,
                "is_override": True,
            }

        default_message = DEFAULT_IVR_PROMPTS.get(key)
        if default_message is None:
            raise HTTPException(status_code=404, detail="IVR prompt not found")

        return {
            "id": None,
            "key": key,
            "message": default_message,
            "updated_at": None,
            "is_override": False,
        }
    finally:
        db.close()


@router.put("/ivr-prompts/{key}")
async def upsert_ivr_prompt(key: str, data: IVRPromptUpdate):
    """Create or update an IVR prompt text for the given key."""
    if key not in DEFAULT_IVR_PROMPTS:
        raise HTTPException(status_code=400, detail="Invalid IVR prompt key")

    db = SessionLocal()
    try:
        prompt = db.query(VoicePrompt).filter(VoicePrompt.key == key).first()
        if prompt:
            prompt.message = data.message
        else:
            prompt = VoicePrompt(key=key, message=data.message)
            db.add(prompt)

        db.commit()
        config_service.refresh_cache(force=True)
        log_event(None, "IVR_PROMPT_UPSERTED", {"key": key})

        return {
            "status": "upserted",
            "key": key,
            "message": data.message,
            "is_override": True,
        }
    finally:
        db.close()


@router.delete("/ivr-prompts/{key}")
async def delete_ivr_prompt(key: str):
    """Delete an override for an IVR prompt (fallback default will be used)."""
    if key not in DEFAULT_IVR_PROMPTS:
        raise HTTPException(status_code=400, detail="Invalid IVR prompt key")

    db = SessionLocal()
    try:
        prompt = db.query(VoicePrompt).filter(VoicePrompt.key == key).first()
        if prompt:
            db.delete(prompt)
            db.commit()
            config_service.refresh_cache(force=True)
            log_event(None, "IVR_PROMPT_DELETED", {"key": key})

        return {
            "status": "deleted",
            "key": key,
            "is_override": False,
            "message": DEFAULT_IVR_PROMPTS.get(key),
        }
    finally:
        db.close()


@router.get("/greetings/{language}")
async def get_greeting(language: str):
    """Fetch the greeting for a specific language."""
    db = SessionLocal()
    try:
        greeting = db.query(VoiceGreeting).filter(VoiceGreeting.language == language).first()
        if greeting:
            return {
                "id": greeting.id,
                "language": greeting.language,
                "message": greeting.message,
                "updated_at": greeting.updated_at,
                "is_override": True,
            }

        default_message = DEFAULT_GREETINGS.get(language)
        if default_message is None:
            raise HTTPException(status_code=404, detail="Greeting not found")

        return {
            "id": None,
            "language": language,
            "message": default_message,
            "updated_at": None,
            "is_override": False,
        }
    finally:
        db.close()


@router.put("/greetings/{language}")
async def upsert_greeting(language: str, data: GreetingUpdate):
    """Create or update a greeting for a language."""
    db = SessionLocal()
    try:
        greeting = db.query(VoiceGreeting).filter(VoiceGreeting.language == language).first()
        if greeting:
            greeting.message = data.message
        else:
            greeting = VoiceGreeting(language=language, message=data.message)
            db.add(greeting)

        db.commit()
        config_service.refresh_cache(force=True)
        log_event(None, "GREETING_UPSERTED", {"language": language})

        return {
            "status": "upserted",
            "language": language,
            "message": data.message,
            "is_override": True,
        }
    finally:
        db.close()


@router.delete("/greetings/{language}")
async def delete_greeting(language: str):
    """Delete a greeting override for a language (fallback will be used)."""
    db = SessionLocal()
    try:
        greeting = db.query(VoiceGreeting).filter(VoiceGreeting.language == language).first()
        if greeting:
            db.delete(greeting)
            db.commit()
            config_service.refresh_cache(force=True)
            log_event(None, "GREETING_DELETED", {"language": language})
        else:
            default_exists = language in DEFAULT_GREETINGS
            if not default_exists:
                raise HTTPException(status_code=404, detail="Greeting not found")

        return {
            "status": "deleted",
            "language": language,
            "is_override": False,
            "message": DEFAULT_GREETINGS.get(language),
        }
    finally:
        db.close()


# ==================== AGENT ENDPOINTS ====================

@router.get("/agents")
async def list_agents():
    """List all agents with their specializations."""
    db = SessionLocal()
    try:
        agents = db.query(Agent).order_by(Agent.region, Agent.name).all()
        result = []
        for a in agents:
            specs = db.query(AgentSpecialization).filter(AgentSpecialization.agent_id == a.id).all()
            result.append({
                "id": a.id,
                "name": a.name,
                "phone_number": a.phone_number,
                "region": a.region,
                "is_active": a.is_active,
                "is_default": a.is_default,
                "specializations": [
                    {"category": s.category, "proficiency": s.proficiency_level}
                    for s in specs
                ],
            })
        return result
    finally:
        db.close()


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: int):
    """Get a specific agent."""
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        specs = db.query(AgentSpecialization).filter(AgentSpecialization.agent_id == agent.id).all()
        return {
            "id": agent.id,
            "name": agent.name,
            "phone_number": agent.phone_number,
            "region": agent.region,
            "is_active": agent.is_active,
            "is_default": agent.is_default,
            "specializations": [
                {"category": s.category, "proficiency": s.proficiency_level}
                for s in specs
            ],
        }
    finally:
        db.close()


@router.post("/agents")
async def create_agent(data: AgentCreate):
    """Create a new agent with optional specializations."""
    db = SessionLocal()
    try:
        agent = Agent(
            name=data.name,
            phone_number=data.phone_number,
            region=data.region.upper(),
            is_default=data.is_default,
            is_active=True,
        )
        db.add(agent)
        db.flush()  # Get agent.id
        
        # Add specializations
        for cat in data.specializations:
            spec = AgentSpecialization(
                agent_id=agent.id,
                category=cat.lower(),
                proficiency_level=1,
            )
            db.add(spec)
        
        db.commit()
        
        config_service.refresh_cache(force=True)
        log_event(None, "AGENT_CREATED", {"name": data.name, "region": data.region})
        
        return {"status": "created", "agent_id": agent.id}
    finally:
        db.close()


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: int, data: AgentUpdate):
    """Update an existing agent."""
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        if data.name is not None:
            agent.name = data.name
        if data.phone_number is not None:
            agent.phone_number = data.phone_number
        if data.region is not None:
            agent.region = data.region.upper()
        if data.is_active is not None:
            agent.is_active = data.is_active
        if data.is_default is not None:
            agent.is_default = data.is_default
        
        db.commit()
        
        config_service.refresh_cache(force=True)
        log_event(None, "AGENT_UPDATED", {"agent_id": agent_id})
        
        return {"status": "updated", "agent_id": agent_id}
    finally:
        db.close()


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: int):
    """Delete an agent (soft delete)."""
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        agent.is_active = False
        db.commit()
        
        config_service.refresh_cache(force=True)
        log_event(None, "AGENT_DELETED", {"agent_id": agent_id})
        
        return {"status": "deleted", "agent_id": agent_id}
    finally:
        db.close()


@router.post("/agents/{agent_id}/specializations")
async def add_specialization(agent_id: int, data: SpecializationAdd):
    """Add a specialization to an agent."""
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Check if already exists
        existing = db.query(AgentSpecialization).filter(
            AgentSpecialization.agent_id == agent_id,
            AgentSpecialization.category == data.category.lower()
        ).first()
        
        if existing:
            existing.proficiency_level = data.proficiency_level
        else:
            spec = AgentSpecialization(
                agent_id=agent_id,
                category=data.category.lower(),
                proficiency_level=data.proficiency_level,
            )
            db.add(spec)
        
        db.commit()
        
        config_service.refresh_cache(force=True)
        log_event(None, "SPECIALIZATION_ADDED", {"agent_id": agent_id, "category": data.category})
        
        return {"status": "added", "category": data.category}
    finally:
        db.close()


@router.delete("/agents/{agent_id}/specializations/{category}")
async def remove_specialization(agent_id: int, category: str):
    """Remove a specialization from an agent."""
    db = SessionLocal()
    try:
        spec = db.query(AgentSpecialization).filter(
            AgentSpecialization.agent_id == agent_id,
            AgentSpecialization.category == category.lower()
        ).first()
        
        if not spec:
            raise HTTPException(status_code=404, detail="Specialization not found")
        
        db.delete(spec)
        db.commit()
        
        config_service.refresh_cache(force=True)
        log_event(None, "SPECIALIZATION_REMOVED", {"agent_id": agent_id, "category": category})
        
        return {"status": "removed", "category": category}
    finally:
        db.close()


# ==================== CORRECTION ENDPOINTS ====================

@router.get("/corrections")
async def list_corrections():
    """List all misheard word corrections."""
    db = SessionLocal()
    try:
        corrections = db.query(MisheardCorrection).filter(MisheardCorrection.is_active == True).all()
        return [
            {
                "id": c.id,
                "wrong_word": c.wrong_word,
                "correct_word": c.correct_word,
            }
            for c in corrections
        ]
    finally:
        db.close()


@router.post("/corrections")
async def create_correction(data: CorrectionCreate):
    """Add a new misheard word correction."""
    db = SessionLocal()
    try:
        correction = MisheardCorrection(
            wrong_word=data.wrong_word.lower(),
            correct_word=data.correct_word.lower(),
            is_active=True,
        )
        db.add(correction)
        db.commit()
        
        config_service.refresh_cache(force=True)
        log_event(None, "CORRECTION_CREATED", {"wrong": data.wrong_word, "correct": data.correct_word})
        
        return {"status": "created", "wrong_word": data.wrong_word}
    finally:
        db.close()


@router.delete("/corrections/{correction_id}")
async def delete_correction(correction_id: int):
    """Delete a correction."""
    db = SessionLocal()
    try:
        correction = db.query(MisheardCorrection).filter(MisheardCorrection.id == correction_id).first()
        if not correction:
            raise HTTPException(status_code=404, detail="Correction not found")
        
        correction.is_active = False
        db.commit()
        
        config_service.refresh_cache(force=True)
        
        return {"status": "deleted"}
    finally:
        db.close()


# ==================== CACHE MANAGEMENT ====================

@router.post("/refresh-cache")
async def refresh_cache():
    """Force refresh the configuration cache."""
    config_service.refresh_cache(force=True)
    return {"status": "refreshed"}


@router.get("/cache-status")
async def cache_status():
    """Get current cache status."""
    return {
        "greetings_count": len(config_service._cache.get("greetings", {})),
        "agents_count": len(config_service._cache.get("agents", [])),
        "corrections_count": len(config_service._cache.get("corrections", {})),
        "last_refresh": str(config_service._cache.get("last_refresh")),
    }
