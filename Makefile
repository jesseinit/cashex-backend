prod:
	@echo "Staring Up Production Server"
	daphne config.asgi:application --port $PORT --bind 0.0.0.0 -v2

make-migrations:
	@echo "Generating Migrations"
	python manage.py makemigrations

migrate:
	@echo "Running Migrations"
	python manage.py migrate

dev:
	@echo "Staring Up Dev Server"
	python manage.py runserver

workers:
	@echo "Staring Up Celery Workers"
	celery -A config worker --loglevel=info

test:
	@echo "Running Tests"
	pytest -vs
