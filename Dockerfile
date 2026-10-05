ARG BASE_IMAGE=ubuntu:latest
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/opt/venv/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl nginx python3 python3-venv supervisor \
       openjdk-21-jdk-headless maven \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/app

COPY requirements.txt /opt/app/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r /opt/app/requirements.txt \
    && /opt/venv/bin/python -c 'from cryptography.hazmat.primitives.ciphers.aead import AESGCM; print("AES-256-GCM support: OK")'

COPY app/ /opt/app/
COPY scripts/data-manager.py /usr/local/bin/codex-data-manager
COPY data/biff-2026/seed.json /opt/biff-data/seed.json
COPY docker/nginx/default.conf /etc/nginx/sites-available/default
COPY docker/supervisor/codex.conf /etc/supervisor/conf.d/codex.conf
COPY docker/entrypoint.sh /usr/local/bin/codex-entrypoint

# Java 21 / javac / Maven integration.  Building here proves that all three
# toolchain components work in the final Ubuntu container image.
COPY java-biff-planner/ /opt/java-biff-planner/
RUN java -version \
    && javac -version \
    && mvn -version \
    && mvn -B -ntp -f /opt/java-biff-planner/pom.xml clean package \
    && java -jar /opt/java-biff-planner/target/biff-planner-1.0.0.jar toolchain

RUN mkdir -p /data \
    && chmod 0755 /usr/local/bin/codex-entrypoint /usr/local/bin/codex-data-manager \
    && /opt/venv/bin/python /usr/local/bin/codex-data-manager --db /tmp/managed-data.db init \
    && /opt/venv/bin/python /usr/local/bin/codex-data-manager --db /tmp/managed-data.db import /opt/biff-data/seed.json \
    && /opt/venv/bin/python /usr/local/bin/codex-data-manager --db /tmp/managed-data.db verify \
    && rm -f /tmp/managed-data.db \
    && chown -R www-data:www-data /data /opt/app

VOLUME ["/data"]

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=8s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/healthz || exit 1

CMD ["/usr/local/bin/codex-entrypoint"]
