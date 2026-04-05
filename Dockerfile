FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

RUN chmod +x /app/docker/web-entrypoint.sh \
    && groupadd --system appuser \
    && useradd --system --gid appuser --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/staticfiles /app/media /app/runtime_logs \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["/app/docker/web-entrypoint.sh"]
