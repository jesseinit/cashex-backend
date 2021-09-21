#!/bin/sh

# source venv/bin/activate
source .env

while ! nc -z cashex-db 5432; do echo 'Waiting for Postgres Database Startup' & sleep 1; done;

echo "<<<<<<<<<< Running Migrations >>>>>>>>>>"
python manage.py makemigrations && python manage.py migrate
echo "<<<<<<<<<< Migrations Completed >>>>>>>>>>"

# echo "<<<<<<<<<< Starting ${ENV^^} Server>>>>>>>>>>"
# if [ $ENV == 'production' ]
# then
# gunicorn config.wsgi -w 9 -b 0.0.0.0:8000 --worker-class=gevent --worker-connections=1000 --access-logfile gunicorn.log --capture-output
# else
# gunicorn config.wsgi -w 4 -b 0.0.0.0:8000 --worker-class=gevent --worker-connections=1000 --access-logfile gunicorn.log --capture-output --reload
# fi

daphne config.asgi:application --port 8000 --bind 0.0.0.0
