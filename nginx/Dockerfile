# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────
#  Maa-Web · nginx reverse proxy + static frontend
#  Multi-stage:
#    1) frontend-builder (node 20 alpine)  → npm ci → npm run build → dist/
#    2) runtime (nginx:1.27-alpine)        → COPY dist + default.conf
#
#  Build context is REPO ROOT (set via docker-compose build.context: .)
#  so relative paths in this Dockerfile are relative to d:\Maa-Web\ (repo root).
# ─────────────────────────────────────────────────────────

# ── Stage 1: build Vue3 frontend ────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /src

# Install deps first (good caching when package.json hasn't changed)
COPY frontend/package.json frontend/package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    if [ -f package-lock.json ]; then \
        npm ci --no-audit --no-fund; \
    else \
        npm install --no-audit --no-fund; \
    fi

# Copy source & build
COPY frontend/ ./
RUN npm run build

# ── Stage 2: runtime nginx ──────────────────────────────
FROM nginx:1.27-alpine AS runtime

LABEL org.opencontainers.image.title="Maa-Web Nginx (static + reverse proxy)" \
      org.opencontainers.image.authors="Maa-Web Contributors" \
      org.opencontainers.image.licenses="MIT"

# ── Security hardening:
#    - Run as nginx (UID 101 in alpine) — avoid root
#    - Listen on 8080 (>1024) so non-root bind works
#    - /var/cache/nginx, /var/run need to be writable by nginx user
RUN set -eux; \
    # Writable dirs for non-root nginx
    mkdir -p /var/cache/nginx /run /var/run /tmp/nginx_body /tmp/nginx_proxy; \
    chown -R nginx:nginx /var/cache/nginx /var/run /tmp/nginx_body /tmp/nginx_proxy /etc/nginx/conf.d; \
    # /var/run is a symlink → ../run; chown -R only touched the link itself,
    # nginx.conf hardcodes pid /run/nginx.pid so /run itself must be writable.
    chown nginx:nginx /run; \
    # Remove default config
    rm -f /etc/nginx/conf.d/default.conf

# Drop privileges (USER before COPY so files end up owned by root but readable)
USER nginx

# ── Static site: built frontend ─────────────────────────
COPY --from=frontend-builder --chown=nginx:nginx /src/dist /usr/share/nginx/html

# ── Reverse proxy config ────────────────────────────────
COPY --chown=nginx:nginx nginx/default.conf /etc/nginx/conf.d/default.conf

# Expose non-privileged port (matches docker-compose port mapping)
EXPOSE 8080

# Use SIGQUIT (nginx "graceful shutdown") instead of default SIGTERM
STOPSIGNAL SIGQUIT

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://127.0.0.1:8080/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
