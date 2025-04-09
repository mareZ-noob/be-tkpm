import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()


def make_celery(app_name=__name__):
    celery = Celery(
        app_name,
        broker=f"redis://{os.getenv('REDIS_HOST')}:{os.getenv('REDIS_PORT')}/0",
        backend=f"redis://{os.getenv('REDIS_HOST')}:{os.getenv('REDIS_PORT')}/0",
        include=[
            'app.tasks.email_tasks',
            'app.tasks.upload_tasks',
        ]
    )

    celery.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        worker_max_tasks_per_child=1000
    )

    return celery
