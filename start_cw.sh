#!/bin/sh

# source venv/bin/activate
source .env

# if [ $ENV == 'production' ] || [ $ENV == 'staging' ]
# then
# while ! nc -z host.docker.internal 6379; do echo 'Waiting for Redis Database Startup' & sleep 1; done;
# else
# while ! nc -z tudo-redis 6379; do echo 'Waiting for Redis Database Startup' & sleep 1; done;
# fi

while ! nc -z cashex-redis 6379; do echo 'Waiting for Redis Database Startup' & sleep 1; done;

echo "<<<<<<<<<< Starting Celery Worker >>>>>>>>>>"
celery -A config worker -l info
