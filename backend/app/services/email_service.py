import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.core.messages import ErrorMessages


def send_email(to_email: str, subject: str, body_text: str) -> None:
    if not settings.SMTP_HOST:
        raise RuntimeError(ErrorMessages.SMTP_HOST_NOT_SET.value)
    if not settings.SMTP_FROM:
        raise RuntimeError(ErrorMessages.SMTP_FROM_NOT_SET.value)

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body_text)

    if settings.SMTP_USE_SSL:
        server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT)
    else:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)

    try:
        server.ehlo()
        if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
            server.starttls()
            server.ehlo()
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass

