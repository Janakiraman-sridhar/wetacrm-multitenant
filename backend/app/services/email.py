import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.settings.models import EmailTemplate, Setting

log = logging.getLogger("weta.email")


def email_configured() -> bool:
    """Whether outbound SMTP is set up. When False, send_email only logs."""
    return bool(settings.smtp_host)


def send_email(
    to: str | list[str],
    subject: str,
    body_html: str,
    attachments: list[tuple[str, bytes, str]] | None = None,  # (filename, data, mime)
    inline_images: list[tuple[str, bytes, str]] | None = None,  # (cid, data, mime)
) -> bool:
    recipients = [to] if isinstance(to, str) else list(to)

    if not settings.smtp_host:
        log.info("[email fallback] To: %s | Subject: %s\n%s", recipients, subject, body_html)
        return False

    msg = MIMEMultipart("mixed")
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    # Inline images (e.g. the app logo) must live in a multipart/related part
    # alongside the HTML so `cid:` references resolve in the mail client.
    if inline_images:
        related = MIMEMultipart("related")
        related.attach(MIMEText(body_html, "html"))
        for cid, data, mime in inline_images:
            img = MIMEImage(data, _subtype=mime.split("/")[-1])
            img.add_header("Content-ID", f"<{cid}>")
            img.add_header("Content-Disposition", "inline", filename=cid)
            related.attach(img)
        msg.attach(related)
    else:
        msg.attach(MIMEText(body_html, "html"))

    for filename, data, mime in attachments or []:
        part = MIMEApplication(data, _subtype=mime.split("/")[-1])
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from, recipients, msg.as_string())
        return True
    except Exception:
        log.exception("Failed to send email to %s", recipients)
        return False


class _SafeDict(dict):
    def __missing__(self, key):  # leave unknown placeholders intact instead of raising
        return "{" + key + "}"


def render_template(db: Session, name: str, context: dict) -> tuple[str, str]:
    """Return (subject, body_html) for a stored template, with {placeholders} filled."""
    tpl = db.scalar(select(EmailTemplate).where(EmailTemplate.name == name))
    if not tpl:
        return name, ""
    ctx = _SafeDict(app_name=settings.app_name, **context)
    return tpl.subject.format_map(ctx), tpl.body_html.format_map(ctx)


def send_templated(db: Session, to: str | list[str], template: str, context: dict, attachments=None, inline_images=None) -> bool:
    subject, body = render_template(db, template, context)
    if not body and not subject:
        return False
    return send_email(to, subject, body, attachments, inline_images)


# --- application branding for emails --------------------------------------

def _sniff_image_mime(data: bytes) -> str:
    if data[:8].startswith(b"\x89PNG"):
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def app_logo(db: Session) -> tuple[bytes, str] | None:
    """The uploaded company/app logo as (bytes, mime), or None if none is set."""
    row = db.scalar(select(Setting).where(Setting.key == "company_profile"))
    key = (row.value if row else {} or {}).get("logo_key")
    if not key:
        return None
    try:
        from app.services import storage

        data = storage.read_file(key)
    except Exception:
        return None
    return data, _sniff_image_mime(data)


def send_welcome(db: Session, user) -> bool:
    """Welcome email including the application logo and a link into the app."""
    ctx: dict = {
        "first_name": user.first_name,
        "email": user.email,
        "app_url": settings.public_app_url,
    }
    inline_images = None
    logo = app_logo(db)
    if logo:
        data, mime = logo
        ctx["logo_html"] = (
            f'<img src="cid:app-logo" alt="{settings.app_name}" '
            f'style="max-height:56px;max-width:220px;margin-bottom:16px" />'
        )
        inline_images = [("app-logo", data, mime)]
    else:
        ctx["logo_html"] = ""
    from app.settings import workflows

    return workflows.fire(db, "welcome", user.email, ctx, inline_images=inline_images)
