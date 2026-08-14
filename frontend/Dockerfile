# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────
#  Maa-Web · frontend standalone builder (for local use / CI artifact).
#
#  NOTE: For production deploy, the nginx/ Dockerfile ALSO builds the frontend
#        in a multi-stage COPY, so this file is optional convenience.
# ─────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install deps first (better layer caching)
COPY package.json package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    if [ -f package-lock.json ]; then \
        npm ci; \
    else \
        npm install; \
    fi

# Copy source & build
COPY . .
RUN npm run build

# Final stage: just output dist.
# When using this standalone image: you can bind-mount the /app/dist volume
# to share with an nginx container.
FROM scratch AS dist
COPY --from=builder /app/dist /dist
