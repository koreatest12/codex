ARG BASE_IMAGE=ubuntu:latest
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/opt/venv/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl nginx python3 python3-venv supervisor \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/app

COPY requirements.txt /opt/app/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r /opt/app/requirements.txt

COPY app/ /opt/app/
COPY docker/nginx/default.conf /etc/nginx/sites-available/default
COPY docker/supervisor/codex.conf /etc/supervisor/conf.d/codex.conf

RUN mkdir -p /data \
    && chown -R www-data:www-data /data /opt/app

VOLUME ["/data"]

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=8s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/healthz || exit 1

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/codex.conf"]
