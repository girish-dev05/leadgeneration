import smtplib
from email.message import EmailMessage
from pathlib import Path

from app.config import get_settings
from app.models import Lead

settings = get_settings()


class EmailService:
    def send_proposal_email(self, lead: Lead, subject: str, body: str, pdf_path: str) -> tuple[bool, str]:
        if not lead.email:
            return False, 'lead_missing_email'

        if not settings.smtp_user or not settings.smtp_password or not settings.smtp_from:
            return False, 'smtp_not_configured'

        message = EmailMessage()
        message['From'] = settings.smtp_from
        message['To'] = lead.email
        message['Subject'] = subject
        message.set_content(body)

        pdf_bytes = Path(pdf_path).read_bytes()
        message.add_attachment(
            pdf_bytes,
            maintype='application',
            subtype='pdf',
            filename=Path(pdf_path).name,
        )

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(message)
            return True, 'sent'
        except Exception as exc:
            return False, f'failed: {exc}'
