import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()


def make_celery(app_name=__name__):
    broker_url = f"redis://{os.getenv('REDIS_USERNAME')}:{os.getenv('REDIS_PASSWORD')}@{os.getenv('REDIS_HOST')}:{os.getenv('REDIS_PORT')}/0"
    result_backend = f"redis://{os.getenv('REDIS_USERNAME')}:{os.getenv('REDIS_PASSWORD')}@{os.getenv('REDIS_HOST')}:{os.getenv('REDIS_PORT')}/0"

    celery = Celery(
        app_name,
        broker=broker_url,
        backend=result_backend,
        include=[
            'app.tasks.email_tasks',
            'app.tasks.upload_tasks',
            'app.tasks.image_tasks',
            'app.tasks.youtube_tasks',
            'app.tasks.video_tasks',
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
        worker_max_tasks_per_child=1000,
        broker_pool_limit=50,
        redis_max_connections=100,
        broker_connection_timeout=10,
        broker_connection_retry=True,
        broker_connection_max_retries=3,
        broker_heartbeat=10,
        broker_transport_options={
            'visibility_timeout': 3600,
            'socket_timeout': 30,
            'socket_connect_timeout': 30,
            'socket_keepalive': True
        }
    )

    return celery
