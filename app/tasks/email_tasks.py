from flask_mail import Message

from app.config.extensions import celery, mail


@celery.task(bind=True, max_retries=3, default_retry_delay=300)
def send_email_task(self, subject, recipients, body, html):
    """
    Celery task for sending emails asynchronously

    Args:
        subject (str): Email subject
        recipients (list): List of recipient email addresses
        body (str): Plain text email body
        html (str): HTML email body

    Returns:
        bool: Success status
    """
    try:
        msg = Message(subject=subject, recipients=recipients, body=body, html=html)
        mail.send(msg)
        return True
    except Exception as exc:
        # Retry with exponential backoff
        self.retry(exc=exc)
