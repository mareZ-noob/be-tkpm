web: gunicorn -w 4 -b 0.0.0.0:5000 "run:app"
worker: celery -A celery_worker.celery worker --concurrency=20 --loglevel=info