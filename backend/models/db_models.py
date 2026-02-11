"""SQLAlchemy models for call/AI/routing analytics.

These correspond to the Postgres tables described in the design:
- calls
- call_events
- routing_decisions
- agent_assignments
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.db import Base


class Call(Base):
    __tablename__ = "calls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    twilio_call_sid = Column(String(64), unique=True, nullable=False)

    from_number = Column(String(20))
    to_number = Column(String(20))

    caller_country = Column(CHAR(2))
    caller_state = Column(String(50))
    caller_city = Column(String(50))

    call_start = Column(DateTime, nullable=False, default=datetime.utcnow)
    call_end = Column(DateTime)

    final_handler = Column(String(10))
    call_status = Column(String(20))

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "final_handler IN ('AI', 'HUMAN')",
            name="calls_final_handler_check",
        ),
        Index("idx_calls_twilio_sid", "twilio_call_sid"),
    )


class CallEvent(Base):
    __tablename__ = "call_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    call_id = Column(UUID(as_uuid=True), ForeignKey("calls.id"))

    event_type = Column(String(50), nullable=False)
    event_payload = Column(JSONB)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_events_call_id", "call_id"),
    )


class CallLead(Base):
    __tablename__ = "call_leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_id = Column(UUID(as_uuid=True), ForeignKey("calls.id"))
    call_sid = Column(String(64), unique=True, nullable=False)

    page_context = Column(String(20), nullable=False, default="home")
    selected_category = Column(String(50))
    currency = Column(String(3))
    preferred_language = Column(String(10))
    user_type = Column(String(20))
    customer_id = Column(String(100))
    product_id = Column(String(100))
    extra_metadata = Column(JSONB)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_call_leads_call_sid", "call_sid"),
    )


class RoutingDecision(Base):
    __tablename__ = "routing_decisions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    call_id = Column(UUID(as_uuid=True), ForeignKey("calls.id"))

    caller_country = Column(CHAR(2))
    routing_rule = Column(String(50))  # e.g. 'CALLER_COUNTRY'
    routed_to = Column(String(50))     # e.g. 'US_AGENT_POOL'

    decided_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_routing_call_id", "call_id"),
    )


class AgentAssignment(Base):
    __tablename__ = "agent_assignments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    call_id = Column(UUID(as_uuid=True), ForeignKey("calls.id"))

    agent_id = Column(String(50))
    agent_region = Column(String(10))  # US / IN
    agent_type = Column(String(20))    # HUMAN

    assigned_at = Column(DateTime)
    disconnected_at = Column(DateTime)

    __table_args__ = (
        Index("idx_agent_call_id", "call_id"),
    )


# ==================== CONFIGURABLE AGENTS ====================

class Agent(Base):
    """Agent profiles with phone numbers and specializations."""
    __tablename__ = "agents"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    phone_number = Column(String(20), nullable=False)
    region = Column(String(10), nullable=False)  # 'US', 'IN', 'GLOBAL'
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)  # Default agent for region if no specialist match
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_agents_region", "region"),
        Index("idx_agents_active", "is_active"),
    )


class AgentSpecialization(Base):
    """Many-to-many: Agent can specialize in multiple jewelry categories."""
    __tablename__ = "agent_specializations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_id = Column(BigInteger, ForeignKey("agents.id"), nullable=False)
    category = Column(String(50), nullable=False)  # e.g., 'necklace', 'polki', 'bridal'
    proficiency_level = Column(BigInteger, default=1)  # 1=basic, 2=intermediate, 3=expert
    
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_spec_agent", "agent_id"),
        Index("idx_spec_category", "category"),
    )


# ==================== MISHEARD WORD CORRECTIONS ====================

class MisheardCorrection(Base):
    """Configurable STT misheard word corrections."""
    __tablename__ = "misheard_corrections"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    wrong_word = Column(String(50), nullable=False)  # What STT might hear
    correct_word = Column(String(50), nullable=False)  # What it should be
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_misheard_wrong", "wrong_word"),
    )


class VoiceGreeting(Base):
    """Stores IVR greeting copy per language."""

    __tablename__ = "voice_greetings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    language = Column(String(10), nullable=False, unique=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VoicePrompt(Base):
    """Stores configurable IVR prompt copy (menu, reprompt, confirmation, invalid)."""

    __tablename__ = "voice_prompts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    key = Column(String(50), nullable=False, unique=True)  # e.g., 'menu', 'reprompt', 'confirmation', 'invalid'
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
