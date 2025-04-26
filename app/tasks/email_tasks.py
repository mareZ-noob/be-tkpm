from flask_mail import Message

from app.config.extensions import celery, mail


@celery.task(bind=True, max_retries=3)
def send_email_task(self, subject, recipients, body, html):
    try:
        msg = Message(subject=subject, recipients=recipients, body=body, html=html)
        mail.send(msg)
        return {'msg': 'success'}
    except Exception as exc:
        try:
            self.retry(exc=exc, countdown=5 * 30)
        except self.MaxRetriesExceededError as e:
            return {'msg': 'failed', 'error': str(e)}
