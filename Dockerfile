ARG BASE_IMAGE=ubuntu:latest
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY docker/nginx/default.conf /etc/nginx/sites-available/default
COPY docker/www/index.html /var/www/html/index.html

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
