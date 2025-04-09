# from concurrent.futures import ThreadPoolExecutor
#
# from flask import current_app
# from flask_mail import Message
#
# from app.config.extensions import mail
#
# executor = ThreadPoolExecutor(max_workers=5)
#
#
# def send_email_async(app, msg):
#     with app.app_context():
#         try:
#             mail.send(msg)
#         except Exception as e:
#             print(f"Error sending email: {str(e)}")
#
#
# def send_email(subject, recipients, body, html):
#     msg = Message(subject=subject, recipients=recipients, body=body, html=html)
#     app = current_app._get_current_object()
#     executor.submit(send_email_async, app, msg)
#     return True

from app.tasks.email_tasks import send_email_task


def send_email(subject, recipients, body, html):
    task_result = send_email_task.delay(subject, recipients, body, html)
    return task_result
