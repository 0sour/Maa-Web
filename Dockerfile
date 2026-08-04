FROM node:20-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        adb \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install --omit=dev

COPY server ./server
COPY public ./public
COPY bin/maa ./bin/maa
RUN chmod +x ./bin/maa

ENV PORT=3100 \
    MAA_CONFIG_DIR=/config \
    XDG_DATA_HOME=/data \
    XDG_STATE_HOME=/state

VOLUME ["/config", "/data", "/state"]

EXPOSE 3100

CMD ["node", "server/index.js"]
