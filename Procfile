web: python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 2 --timeout-keep-alive 30
worker: celery -A app.worker worker --loglevel=info --concurrency=2
release: alembic upgrade head
