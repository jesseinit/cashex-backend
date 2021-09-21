web: daphne config.asgi:application --port $PORT --bind 0.0.0.0 -v2
worker: python manage.py runworker channel_layer -v2
worker1: celery -A config worker --loglevel=info
release: python manage.py migrate --noinput
