"""Plivo telephony provider implementation generating Plivo Voice XML."""

from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET
import re
from fastapi import Request, Response

from app.providers.base import BaseTelephonyProvider


class PlivoGetInputWrapper:
    """Wrapper for <GetInput> XML element."""

    def __init__(self, element: ET.Element):
        self.element = element

    def add_speak(
        self,
        text: str,
        voice: str = "Polly.Aditi",
        language: str = "en-IN",
    ) -> None:
        """Add <Speak> prompt inside <GetInput>."""
        _append_speak(self.element, text, voice, language)


class PlivoXmlDocument:
    """Plivo Voice XML document builder."""

    def __init__(self):
        self.root = ET.Element("Response")

    def add_speak(
        self,
        text: str,
        voice: str = "Polly.Aditi",
        language: str = "en-IN",
    ) -> None:
        """Add a top-level <Speak> element."""
        _append_speak(self.root, text, voice, language)

    def add_get_input(
        self,
        action: str,
        method: str = "POST",
        input_type: str = "dtmf speech",
        speech_model: str = "command_and_search",
        language: str = "en-IN",
        hints: Optional[str] = None,
        execution_timeout: int = 20,
        speech_end_timeout: int = 2,
    ) -> PlivoGetInputWrapper:
        """Add a <GetInput> element to collect speech or DTMF."""
        attribs = {
            "action": action,
            "method": method.upper(),
            "inputType": input_type,
            "speechModel": speech_model,
            "language": language,
            "executionTimeout": str(execution_timeout),
            "speechEndTimeout": str(speech_end_timeout),
        }
        if hints:
            attribs["hints"] = hints

        elem = ET.SubElement(self.root, "GetInput", attribs)
        return PlivoGetInputWrapper(elem)

    def add_dial(
        self,
        numbers: List[str],
        caller_id: Optional[str] = None,
        action: Optional[str] = None,
        method: str = "POST",
        timeout: int = 120,
    ) -> None:
        """Add <Dial> with nested <Number> elements."""
        attribs = {
            "timeout": str(timeout),
            "method": method.upper(),
        }
        if caller_id:
            attribs["callerId"] = caller_id
        if action:
            attribs["action"] = action

        dial_elem = ET.SubElement(self.root, "Dial", attribs)
        for num in numbers:
            clean_num = num.strip()
            if clean_num:
                num_elem = ET.SubElement(dial_elem, "Number")
                num_elem.text = clean_num

    def add_redirect(self, url: str, method: str = "POST") -> None:
        """Add a <Redirect> element."""
        redir = ET.SubElement(self.root, "Redirect", {"method": method.upper()})
        redir.text = url

    def add_hangup(self) -> None:
        """Add a <Hangup> element."""
        ET.SubElement(self.root, "Hangup")

    def to_xml(self) -> str:
        """Render to XML string."""
        return ET.tostring(self.root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def _append_speak(parent: ET.Element, text: str, voice: str, language: str) -> None:
    if not text:
        return
    clean_text = re.sub(r"\s+", " ", text).strip()
    speak = ET.SubElement(parent, "Speak", {"voice": voice, "language": language})
    speak.text = clean_text


class PlivoProvider(BaseTelephonyProvider):
    """Plivo telephony provider handling Plivo Voice XML."""

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
        return "plivo"

    def extract_call_metadata(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize parameters from Plivo webhook form or query params."""
        call_sid = (
            data.get("CallUUID")
            or data.get("call_uuid")
            or data.get("CallSid")
            or data.get("call_sid")
        )
        from_number = data.get("From") or data.get("from")
        to_number = data.get("To") or data.get("to")
        speech_result = (
            data.get("SpeechResult")
            or data.get("speech_result")
            or data.get("Digits")
            or data.get("digits")
            or data.get("Speech")
            or data.get("speech")
            or data.get("Text")
            or data.get("text")
        )

        return {
            "call_sid": call_sid,
            "from_number": from_number,
            "to_number": to_number,
            "caller_country": "IN",
            "speech_result": speech_result,
            "provider": "plivo",
        }

    def format_action_url(self, request: Request, path: str) -> str:
        """CRITICAL: Build fully-qualified absolute HTTPS URL for Plivo."""
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
        if proto == "http" and "ngrok" in (request.headers.get("host") or ""):
            proto = "https"
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
        base = f"{proto}://{host}".rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return f"{base}{path}"

    def build_speech_prompt(
        self,
        prompt_text: str,
        action_url: str,
        hints: Optional[str] = None,
        timeout: int = 5,
        redirect_fallback_url: Optional[str] = None,
    ) -> PlivoXmlDocument:
        """Build Plivo XML where bot speaks completely first, then caller gets input window with silence detection."""
        doc = PlivoXmlDocument()
        
        # 1. Play bot speech completely first without barge-in interruption
        doc.add_speak(prompt_text, voice=self.voice, language=self.language)

        # 2. Only after speech is over, initiate GetInput
        # Plivo schema constraints: executionTimeout minimum is 5s, speechEndTimeout minimum is 2s
        exec_timeout = max(5, timeout)
        doc.add_get_input(
            action=action_url,
            method="POST",
            input_type="dtmf speech",
            speech_model="command_and_search",
            language=self.speech_language,
            hints=hints,
            execution_timeout=exec_timeout,
            speech_end_timeout=2,
        )

        # 3. If user says nothing within executionTimeout, proceed to fallback instruction
        if redirect_fallback_url:
            doc.add_redirect(redirect_fallback_url)

        return doc

    def build_message_and_redirect(
        self,
        message: str,
        redirect_url: str,
    ) -> PlivoXmlDocument:
        """Speak a message and redirect to another Plivo URL."""
        doc = PlivoXmlDocument()
        doc.add_speak(message, voice=self.voice, language=self.language)
        doc.add_redirect(redirect_url)
        return doc

    def build_dial(
        self,
        numbers: List[str],
        caller_id: Optional[str] = None,
        action_url: Optional[str] = None,
        timeout: int = 120,
        announce_message: Optional[str] = None,
    ) -> PlivoXmlDocument:
        """Build Plivo <Dial> XML."""
        doc = PlivoXmlDocument()
        if announce_message:
            doc.add_speak(announce_message, voice=self.voice, language=self.language)

        doc.add_dial(
            numbers=numbers,
            caller_id=caller_id,
            action=action_url,
            method="POST",
            timeout=timeout,
        )
        return doc

    def build_hangup(self, message: Optional[str] = None) -> PlivoXmlDocument:
        """Build Plivo <Hangup> XML."""
        doc = PlivoXmlDocument()
        if message:
            doc.add_speak(message, voice=self.voice, language=self.language)
        doc.add_hangup()
        return doc

    def render_response(self, response_obj: PlivoXmlDocument) -> Response:
        """Render Plivo XML document into FastAPI XML Response."""
        return Response(content=response_obj.to_xml(), media_type="application/xml")
