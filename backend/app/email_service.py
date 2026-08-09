import smtplib
from email.message import EmailMessage
from app.config import settings


def send_email(to_email: str, subject: str, body: str) -> bool:
    if not settings.smtp_host:
        return False
    message = EmailMessage()
    message['From'] = settings.smtp_from
    message['To'] = to_email
    message['Subject'] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
            if settings.smtp_starttls:
                client.starttls()
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
        return True
    except (OSError, smtplib.SMTPException):
        return False
