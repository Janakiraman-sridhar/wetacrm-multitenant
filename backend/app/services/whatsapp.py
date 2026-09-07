"""Sending on WhatsApp, behind one interface.

Two channels, and the difference matters:

**Click-to-chat** is a `wa.me` link. The agent's own WhatsApp opens with the message
prefilled and *they* press send. No approvals, no fees, no business verification —
which is why it is the default and why an agency can use this on day one. Nothing is
sent from the server, so all this module does for it is record that it happened.

**The Cloud API** sends from the server. It needs a verified Meta Business account, a
dedicated number, and pre-approved templates for any message outside a 24-hour reply
window. Configured per tenant; absent, `provider_for` returns the null provider and
the app keeps working with click-to-chat, in the same way the rest of the system
degrades without Redis or Meilisearch.

Nothing provider-specific escapes `WhatsAppProvider`, so swapping Meta for a BSP
(AiSensy, Interakt, Twilio) is a new subclass and a settings change.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.settings.models import Setting

log = logging.getLogger("weta.whatsapp")

GRAPH_VERSION = "v21.0"


@dataclass
class SendResult:
    ok: bool
    provider_message_id: str | None = None
    error: str | None = None


def normalise_number(phone: str | None, default_country: str = "91") -> str | None:
    """Digits only, with a country code — the shape both `wa.me` and the API want."""
    if not phone:
        return None
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if len(digits) < 10:
        return None
    return f"{default_country}{digits}" if len(digits) == 10 else digits


def click_to_chat_link(phone: str | None, message: str | None = None) -> str | None:
    number = normalise_number(phone)
    if not number:
        return None
    if message:
        return f"https://wa.me/{number}?text={urllib.parse.quote(message)}"
    return f"https://wa.me/{number}"


class WhatsAppProvider(ABC):
    """What every channel must be able to do. Keep this small."""

    name = "base"
    can_send = False

    @abstractmethod
    def send_text(self, to: str, body: str) -> SendResult: ...

    @abstractmethod
    def send_media(self, to: str, media_bytes: bytes, filename: str, caption: str | None) -> SendResult: ...

    @abstractmethod
    def send_template(self, to: str, template_name: str, params: list[str]) -> SendResult: ...


class NullProvider(WhatsAppProvider):
    """No API configured. Messages are composed for the agent to send themselves.

    Returns a clear failure rather than pretending, so a caller never reports a
    message as sent when nothing left the building.
    """

    name = "click_to_chat"
    can_send = False

    def _refuse(self) -> SendResult:
        return SendResult(
            ok=False,
            error="WhatsApp API is not configured for this workspace. Use the click-to-chat link instead.",
        )

    def send_text(self, to, body):
        return self._refuse()

    def send_media(self, to, media_bytes, filename, caption):
        return self._refuse()

    def send_template(self, to, template_name, params):
        return self._refuse()


class MetaCloudProvider(WhatsAppProvider):
    """Meta's WhatsApp Cloud API.

    Outside a 24-hour window since the customer last replied, Meta only accepts a
    pre-approved template — a plain text send will be rejected. `send_template` is
    therefore the right call for anything the agency initiates, which is most of what
    an insurance workspace sends.
    """

    name = "meta_cloud"
    can_send = True

    def __init__(self, phone_number_id: str, access_token: str):
        self.phone_number_id = phone_number_id
        self.access_token = access_token

    def _post(self, payload: dict) -> SendResult:
        url = f"https://graph.facebook.com/{GRAPH_VERSION}/{self.phone_number_id}/messages"
        request = urllib.request.Request(url, method="POST")
        request.add_header("Authorization", f"Bearer {self.access_token}")
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, json.dumps(payload).encode(), timeout=30) as response:
                body = json.loads(response.read().decode() or "{}")
            message_id = (body.get("messages") or [{}])[0].get("id")
            return SendResult(ok=True, provider_message_id=message_id)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:500]
            log.warning("WhatsApp send rejected (%s): %s", exc.code, detail)
            return SendResult(ok=False, error=f"HTTP {exc.code}: {detail}")
        except Exception as exc:
            log.exception("WhatsApp send failed")
            return SendResult(ok=False, error=str(exc))

    def send_text(self, to: str, body: str) -> SendResult:
        return self._post({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        })

    def send_template(self, to: str, template_name: str, params: list[str]) -> SendResult:
        return self._post({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "en"},
                "components": [{
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(p)} for p in params],
                }],
            },
        })

    def send_media(self, to: str, media_bytes: bytes, filename: str, caption: str | None) -> SendResult:
        # Media must be uploaded to Meta first; the returned id is then sent as the
        # message. Two calls, so a failure in either is reported as one failure here.
        upload_url = f"https://graph.facebook.com/{GRAPH_VERSION}/{self.phone_number_id}/media"
        boundary = "----wetaboundary"
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"messaging_product\"\r\n\r\nwhatsapp\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\nimage/png\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: image/png\r\n\r\n".encode(),
            media_bytes,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
        request = urllib.request.Request(upload_url, method="POST", data=b"".join(parts))
        request.add_header("Authorization", f"Bearer {self.access_token}")
        request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                media_id = json.loads(response.read().decode() or "{}").get("id")
        except Exception as exc:
            log.exception("WhatsApp media upload failed")
            return SendResult(ok=False, error=f"Media upload failed: {exc}")

        if not media_id:
            return SendResult(ok=False, error="Media upload returned no id")

        payload = {"messaging_product": "whatsapp", "to": to, "type": "image",
                   "image": {"id": media_id}}
        if caption:
            payload["image"]["caption"] = caption
        return self._post(payload)


def whatsapp_settings(db: Session) -> dict:
    row = db.scalar(select(Setting).where(Setting.key == "whatsapp"))
    return dict(row.value or {}) if row else {}


def provider_for(db: Session) -> WhatsAppProvider:
    """This workspace's provider, or the null one when the API is not set up."""
    config = whatsapp_settings(db)
    if config.get("enabled") and config.get("phone_number_id") and config.get("access_token"):
        return MetaCloudProvider(config["phone_number_id"], config["access_token"])
    return NullProvider()
