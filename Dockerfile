FROM python:3.9-alpine as build

LABEL maintainer="Jesse Egbosionu <j3bsie@gmail.com>"
WORKDIR /cashex-api

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV TZ=UTC

# RUN apt-get update
# RUN apt-get install -y netcat supervisor 
RUN apk add --no-cache netcat-openbsd supervisor gcc musl-dev python3-dev libffi-dev openssl-dev cargo postgresql-dev jpeg-dev zlib-dev

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN pip install --upgrade pip

COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

FROM python:3.9-alpine

WORKDIR /cashex-api

COPY --from=build /opt/venv /opt/venv

RUN apk add --no-cache netcat-openbsd supervisor gcc musl-dev python3-dev libffi-dev openssl-dev cargo postgresql-dev jpeg-dev zlib-dev

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY . .

CMD [ "supervisord", "-c", "supervisor.cashex.conf" ]
