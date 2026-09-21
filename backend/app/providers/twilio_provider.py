"""Twilio telephony provider implementation generating TwiML."""

from typing import Any, Dict, List, Optional
import math
import re
from fastapi import Request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather, Dial

from app.providers.base import BaseTelephonyProvider


class TwilioProvider(BaseTelephonyProvider):
    """Twilio provider handling TwiML XML formatting."""

    def __init__(
        self,
        voice: str = "Polly.Aditi",
        language: str = "en-IN",
        speech_language: str = "en-IN",
    ) -> None:
        self.voice = voice
        self.language = language
        self.speech_language = speech_language

    @property
    def name(self) -> str:
        return "twilio"

    def extract_call_metadata(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize parameters from Twilio webhook form."""
        call_sid = data.get("CallSid") or data.get("call_sid")
        from_number = data.get("From") or data.get("from")
        to_number = data.get("To") or data.get("to")
        caller_country = data.get("CallerCountry") or data.get("caller_country") or "US"
        speech_result = data.get("SpeechResult") or data.get("speech_result")

        return {
            "call_sid": call_sid,
            "from_number": from_number,
            "to_number": to_number,
            "caller_country": caller_country,
            "speech_result": speech_result,
            "provider": "twilio",
        }

    def format_action_url(self, request: Request, path: str) -> str:
        """For Twilio, standard relative or absolute paths are supported."""
        if not path.startswith("/"):
            path = "/" + path
        return path

    def _say_slow(self, container: Any, text: str, pause_len: float = 0.5) -> None:
        """Speak text in smaller chunks with short pauses."""
        if not text:
            return
        t = re.sub(r"\s+", " ", text).strip()
        chunks = re.split(r"(?<=[\.!?])\s+", t)
        try:
            pause_int = max(1, math.ceil(pause_len))
        except Exception:
            pause_int = 1

        for chunk in chunks:
            if not chunk:
                continue
            sub = [c.strip() for c in chunk.split(",") if c.strip()]
            for piece in sub:
                try:
                    container.say(piece, voice=self.voice, language=self.language)
                except Exception:
                    container.say(piece)
                try:
                    container.pause(length=pause_int)
                except Exception:
                    pass

    def build_speech_prompt(
        self,
        prompt_text: str,
        action_url: str,
        hints: Optional[str] = None,
        timeout: int = 8,
        redirect_fallback_url: Optional[str] = None,
    ) -> VoiceResponse:
        """Build TwiML Gather speech prompt."""
        response = VoiceResponse()
        gather = Gather(
            input="speech",
            action=action_url,
            speech_timeout="auto",
            barge_in=True,
            speech_model="phone_call",
            language=self.speech_language,
            timeout=timeout,
            hints=hints,
        )
        self._say_slow(gather, prompt_text)
        response.append(gather)

        if redirect_fallback_url:
            response.redirect(redirect_fallback_url)

        return response

    def build_message_and_redirect(
        self,
        message: str,
        redirect_url: str,
    ) -> VoiceResponse:
        """Speak a message and redirect to another endpoint."""
        response = VoiceResponse()
        self._say_slow(response, message)
        response.redirect(redirect_url)
        return response

    def build_dial(
        self,
        numbers: List[str],
        caller_id: Optional[str] = None,
        action_url: Optional[str] = None,
        timeout: int = 120,
        announce_message: Optional[str] = None,
    ) -> VoiceResponse:
        """Build TwiML Dial response."""
        response = VoiceResponse()
        if announce_message:
            self._say_slow(response, announce_message)

        dial_kwargs: Dict[str, Any] = {"timeout": timeout}
        if caller_id:
            dial_kwargs["caller_id"] = caller_id
        if action_url:
            dial_kwargs["action"] = action_url

        dial = Dial(**dial_kwargs)
        for num in numbers:
            num_clean = num.strip()
            if num_clean:
                dial.number(num_clean)

        response.append(dial)
        return response

    def build_hangup(self, message: Optional[str] = None) -> VoiceResponse:
        """Build TwiML Hangup response."""
        response = VoiceResponse()
        if message:
            self._say_slow(response, message)
            response.pause(length=2)
        response.hangup()
        return response

    def render_response(self, response_obj: VoiceResponse) -> Response:
        """Render VoiceResponse into FastAPI XML Response."""
        return Response(content=str(response_obj), media_type="application/xml")
