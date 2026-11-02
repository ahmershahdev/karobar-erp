FROM python:3.12-slim-bookworm AS build
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential default-libmysqlclient-dev pkg-config \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements/ requirements/
ARG REQUIREMENTS=base
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements/${REQUIREMENTS}.txt

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends libmariadb3 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --create-home app
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
WORKDIR /app
COPY --chown=app:app . .
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", \
     "--timeout", "30", "--graceful-timeout", "30", "--max-requests", "2000", \
     "--max-requests-jitter", "200", "--limit-request-line", "8190", "--forwarded-allow-ips", "*"]
