"""Abstract base class for telephony providers (Twilio, Plivo, etc.)."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from fastapi import Request, Response


class BaseTelephonyProvider(ABC):
    """Abstract interface defining required telephony XML response operations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name, e.g. 'twilio' or 'plivo'."""
        pass

    @abstractmethod
    def extract_call_metadata(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract normalized call metadata (call_sid, from_number, to_number, speech_result, etc.)."""
        pass

    @abstractmethod
    def format_action_url(self, request: Request, path: str) -> str:
        """Format an action or redirect URL appropriately for this provider."""
        pass

    @abstractmethod
    def build_speech_prompt(
        self,
        prompt_text: str,
        action_url: str,
        hints: Optional[str] = None,
        timeout: int = 8,
        redirect_fallback_url: Optional[str] = None,
    ) -> Any:
        """Build an IVR speech gather/get-input prompt."""
        pass

    @abstractmethod
    def build_message_and_redirect(
        self,
        message: str,
        redirect_url: str,
    ) -> Any:
        """Speak a message and redirect the call to another endpoint."""
        pass

    @abstractmethod
    def build_dial(
        self,
        numbers: List[str],
        caller_id: Optional[str] = None,
        action_url: Optional[str] = None,
        timeout: int = 120,
        announce_message: Optional[str] = None,
    ) -> Any:
        """Transfer/dial out to one or more candidate agent phone numbers."""
        pass

    @abstractmethod
    def build_hangup(self, message: Optional[str] = None) -> Any:
        """Speak an optional final message and hang up the call."""
        pass

    @abstractmethod
    def render_response(self, response_obj: Any) -> Response:
        """Render the provider response object into a FastAPI XML Response."""
        pass
