"""Agent selection and routing logic based on category specialization and region."""

from typing import List, Optional, Tuple
from sqlalchemy import desc

from app.core.database import SessionLocal
from app.models.db_models import Agent, AgentSpecialization
from app.core.logger import log_event

CATEGORY_NORMALIZER = {
    "necklace": "necklace",
    "necklaces": "necklace",
    "bangle": "bangles",
    "bangles": "bangles",
    "bracelet": "bracelets",
    "bracelets": "bracelets",
    "earring": "earrings",
    "earrings": "earrings",
    "ring": "rings",
    "rings": "rings",
    "curated combination": "curated combination",
    "curated combinations": "curated combination",
    "accessory": "accessories",
    "accessories": "accessories",
    "men jewellery": "men jewellery",
    "mens jewellery": "men jewellery",
    "men jewelry": "men jewellery",
    "mens jewelry": "men jewellery",
    "vintage diamonds": "vintage diamonds",
    "vintage diamond": "vintage diamonds",
    "diamond": "vintage diamonds",
    "diamonds": "vintage diamonds",
}


def normalize_category(category: Optional[str]) -> str:
    """Normalize category name to canonical form."""
    if not category:
        return ""
    return CATEGORY_NORMALIZER.get(category.lower().strip(), category.lower().strip())


def region_from_currency(currency: Optional[str]) -> str:
    if (currency or "").upper() == "INR":
        return "IN"
    return "US"


def pick_agent(category: Optional[str], currency: Optional[str]) -> Tuple[Optional[Agent], str]:
    """Return top specialist agent for category plus phone number."""
    canonical_cat = normalize_category(category)
    region = region_from_currency(currency)

    db = SessionLocal()
    try:
        try:
            query = (
                db.query(Agent, AgentSpecialization)
                .join(AgentSpecialization, AgentSpecialization.agent_id == Agent.id)
                .filter(AgentSpecialization.category == canonical_cat)
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

            log_event(None, "NO_AGENT_CONFIGURED", {"category": canonical_cat, "region": region})
            return None, ""
        except Exception as e:
            log_event(None, "AGENT_DB_ERROR", {"error": str(e)})
            return None, ""
    finally:
        db.close()


def get_agent_candidates(category: Optional[str], currency: Optional[str], limit: int = 5) -> List[str]:
    """Return ordered list of phone numbers to try for a category/region."""
    canonical_cat = normalize_category(category)
    region = region_from_currency(currency)

    db = SessionLocal()
    try:
        candidates: List[str] = []

        try:
            # 1. Specialists for requested category
            query = (
                db.query(Agent, AgentSpecialization)
                .join(AgentSpecialization, AgentSpecialization.agent_id == Agent.id)
                .filter(AgentSpecialization.category == canonical_cat)
                .filter(Agent.is_active.is_(True))
                .filter(Agent.region.in_([region, "GLOBAL"]))
                .order_by(desc(AgentSpecialization.proficiency_level), desc(Agent.is_default))
            )
            for agent, _ in query.limit(limit).all():
                if agent.phone_number not in candidates:
                    candidates.append(agent.phone_number)
                    if len(candidates) >= limit:
                        return candidates

            # 2. Specialists from other categories in same region
            if len(candidates) < limit:
                other_query = (
                    db.query(Agent, AgentSpecialization)
                    .join(AgentSpecialization, AgentSpecialization.agent_id == Agent.id)
                    .filter(Agent.is_active.is_(True))
                    .filter(Agent.region.in_([region, "GLOBAL"]))
                    .filter(AgentSpecialization.category != canonical_cat)
                    .order_by(desc(AgentSpecialization.proficiency_level), desc(Agent.is_default))
                )
                for agent, _ in other_query.limit(limit).all():
                    if agent.phone_number not in candidates:
                        candidates.append(agent.phone_number)
                        if len(candidates) >= limit:
                            return candidates

            # 3. Default agents for region
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

            if not candidates:
                log_event(None, "NO_AGENT_CONFIGURED", {"category": canonical_cat, "region": region})

            return candidates
        except Exception as e:
            log_event(None, "AGENT_DB_ERROR", {"error": str(e)})
            return []
    finally:
        db.close()
