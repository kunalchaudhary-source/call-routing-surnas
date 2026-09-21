"""Admin API routes for managing greetings, prompts, agents, settings, and corrections."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.logger import log_event
from app.models.db_models import (
    Agent,
    AgentSpecialization,
    MisheardCorrection,
    VoiceGreeting,
    VoicePrompt,
    AppSetting,
)
from app.models.schemas import (
    LoginRequest,
    DebugModerationRequest,
    AgentCreate,
    AgentUpdate,
    SpecializationAdd,
    CorrectionCreate,
    GreetingUpdate,
    IVRPromptUpdate,
)
from app.services import config_service, gemini_service
from app.services.default_prompts import DEFAULT_GREETINGS, DEFAULT_IVR_PROMPTS

router = APIRouter(prefix="/admin", tags=["admin"])


# ==================== AUTHENTICATION & DIAGNOSTICS ====================

@router.post("/login")
async def login(data: LoginRequest):
    settings = get_settings()
    if data.username == settings.ADMIN_USERNAME and data.password == settings.ADMIN_PASSWORD:
        return {"status": "ok"}
    raise HTTPException(status_code=401, detail="Invalid credentials")


@router.post("/debug/moderation")
async def debug_moderation_endpoint(data: DebugModerationRequest):
    try:
        return gemini_service.debug_moderation(data.text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ==================== APP SETTINGS ====================

class SettingUpdate(BaseModel):
    value: str


@router.get("/settings")
async def list_settings():
    try:
        config_service.refresh_cache()
        settings_dict = getattr(config_service, "_cache", {}).get("settings", {})
        return [{"key": k, "value": v} for k, v in settings_dict.items()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings/{key}")
async def get_setting(key: str):
    val = config_service.get_setting(key)
    if val is None:
        raise HTTPException(status_code=404, detail="Setting not found")
    return {"key": key, "value": val}


@router.put("/settings/{key}")
async def upsert_setting(key: str, data: SettingUpdate):
    db = SessionLocal()
    try:
        setting = db.query(AppSetting).filter_by(key=key).first()
        if setting:
            setting.value = data.value
        else:
            setting = AppSetting(key=key, value=data.value)
            db.add(setting)
        db.commit()
        config_service.refresh_cache(force=True)
        return {"status": "upserted", "key": key, "value": data.value}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


# ==================== IVR PROMPT ENDPOINTS ====================

@router.get("/ivr-prompts")
async def list_ivr_prompts():
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


# ==================== GREETING ENDPOINTS ====================

@router.get("/greetings")
async def list_greetings():
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


@router.get("/greetings/{language}")
async def get_greeting(language: str):
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
    db = SessionLocal()
    try:
        greeting = db.query(VoiceGreeting).filter(VoiceGreeting.language == language).first()
        if greeting:
            db.delete(greeting)
            db.commit()
            config_service.refresh_cache(force=True)
            log_event(None, "GREETING_DELETED", {"language": language})
        else:
            if language not in DEFAULT_GREETINGS:
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
        db.flush()

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
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        existing = db.query(AgentSpecialization).filter(
            AgentSpecialization.agent_id == agent_id,
            AgentSpecialization.category == data.category.lower(),
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
    db = SessionLocal()
    try:
        spec = db.query(AgentSpecialization).filter(
            AgentSpecialization.agent_id == agent_id,
            AgentSpecialization.category == category.lower(),
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
async def refresh_cache_endpoint():
    config_service.refresh_cache(force=True)
    return {"status": "refreshed"}


@router.get("/cache-status")
async def cache_status():
    return {
        "greetings_count": len(config_service._cache.get("greetings", {})),
        "agents_count": len(config_service._cache.get("agents", [])),
        "corrections_count": len(config_service._cache.get("corrections", {})),
        "last_refresh": str(config_service._cache.get("last_refresh")),
    }
