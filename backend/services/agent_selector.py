"""Helpers to locate the best human agent for a given jewelry category."""

from __future__ import annotations

from typing import Optional, Tuple

from sqlalchemy import desc

from backend.config import get_settings
from backend.db import SessionLocal
from backend.models.db_models import Agent, AgentSpecialization
from backend.services.logger import log_event

settings = get_settings()

CATEGORY_NORMALIZER = {
    "necklace": "necklace",
    "necklaces": "necklace",
    "bangle": "bangles",
    "bangles": "bangles",
    "bracelet": "bracelets",
    "bracelets": "bracelets",
    "earring": "earrings",
    "earrings": "earrings",
    "curated combination": "curated combination",
    "curated combinations": "curated combination",
    "accessory": "accessories",
    "accessories": "accessories",
}


def _normalized_category(category: str) -> str:
    return CATEGORY_NORMALIZER.get(category.lower().strip(), category.lower().strip())


def _region_from_currency(currency: Optional[str]) -> str:
    if (currency or "").upper() == "INR":
        return "IN"
    return "US"


def pick_agent(category: str, currency: Optional[str]) -> Tuple[Optional[Agent], str]:
    """Return the most qualified agent for the category plus fallback target number."""
    normalized_category = _normalized_category(category)
    region = _region_from_currency(currency)

    db = SessionLocal()
    try:
        try:
            query = (
                db.query(Agent, AgentSpecialization)
                .join(AgentSpecialization, AgentSpecialization.agent_id == Agent.id)
                .filter(AgentSpecialization.category == normalized_category)
                .filter(Agent.is_active.is_(True))
                .filter(Agent.region.in_([region, "GLOBAL"]))
                .order_by(desc(AgentSpecialization.proficiency_level), desc(Agent.is_default))
            )
            result = query.first()
            if result:
                agent, _ = result
                return agent, agent.phone_number

            default_agent = (
                db.query(Agent)
                .filter(Agent.region == region)
                .filter(Agent.is_active.is_(True))
                .filter(Agent.is_default.is_(True))
                .first()
            )
            if default_agent:
                return default_agent, default_agent.phone_number

            # No agent found in DB — do not fall back to environment-configured pools.
            log_event(None, "NO_AGENT_CONFIGURED", {"category": normalized_category, "region": region})
            return None, ""
        except Exception as e:
            log_event(None, "AGENT_DB_ERROR", {"error": str(e)})
            return None, ""
    finally:
        db.close()


def get_agent_candidates(category: str, currency: Optional[str], limit: int = 5) -> list[str]:
    """Return an ordered list of phone numbers to try for a category.

    The list is ordered by specialist proficiency, region defaults, and finally fallback pools.
    """
    normalized_category = _normalized_category(category)
    region = _region_from_currency(currency)

    db = SessionLocal()
    try:
        candidates = []

        try:
            # Specialist agents for the category (regional first, then GLOBAL)
            query = (
                db.query(Agent, AgentSpecialization)
                .join(AgentSpecialization, AgentSpecialization.agent_id == Agent.id)
                .filter(AgentSpecialization.category == normalized_category)
                .filter(Agent.is_active.is_(True))
                .filter(Agent.region.in_([region, "GLOBAL"]))
                .order_by(desc(AgentSpecialization.proficiency_level), desc(Agent.is_default))
            )
            for agent, _ in query.limit(limit).all():
                if agent.phone_number not in candidates:
                    candidates.append(agent.phone_number)
                    if len(candidates) >= limit:
                        return candidates

            # If we still need more candidates, include specialists from other categories
            if len(candidates) < limit:
                other_query = (
                    db.query(Agent, AgentSpecialization)
                    .join(AgentSpecialization, AgentSpecialization.agent_id == Agent.id)
                    .filter(Agent.is_active.is_(True))
                    .filter(Agent.region.in_([region, "GLOBAL"]))
                    .filter(AgentSpecialization.category != normalized_category)
                    .order_by(desc(AgentSpecialization.proficiency_level), desc(Agent.is_default))
                )
                for agent, _ in other_query.limit(limit).all():
                    if agent.phone_number not in candidates:
                        candidates.append(agent.phone_number)
                        if len(candidates) >= limit:
                            return candidates

            # Default agents for the region
            defaults = (
                db.query(Agent)
                .filter(Agent.region.in_([region, "GLOBAL"]))
                .filter(Agent.is_active.is_(True))
                .filter(Agent.is_default.is_(True))
                .order_by(Agent.region)
                .all()
            )
            for a in defaults:
                if a.phone_number not in candidates:
                    candidates.append(a.phone_number)
                    if len(candidates) >= limit:
                        return candidates

            # Do NOT fall back to environment-configured pools; rely solely on DB
            if not candidates:
                log_event(None, "NO_AGENT_CONFIGURED", {"category": normalized_category, "region": region})

            return candidates
        except Exception as e:
            log_event(None, "AGENT_DB_ERROR", {"error": str(e)})
            return []
    finally:
        db.close()
