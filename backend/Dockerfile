# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────
#  Maa-Web · backend (FastAPI + MaaCore ctypes) Dockerfile
#  Multi-stage: builder (pip install) → slim runtime
#  Runtime: non-root UID=1000/GID=1000
# ─────────────────────────────────────────────────────────

# ── Stage 1: builder ─────────────────────────────────────
# Purpose: install wheels + cache deps, no source needed yet
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

WORKDIR /build

# System deps only for builder (pip wheel cache, not runtime)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
 && rm -rf /var/lib/apt/lists/*

# Copy dependency manifests
COPY pyproject.toml ./
COPY requirements.txt ./

# Install to a dedicated prefix so we can COPY --from in stage 2
# 引擎方案：ctypes 直调 MAA 官方发布包（MaaCore 动态库），由页面
# 「识别资源包」按 MAAWEB_RESOURCE_PLATFORM（linux-aarch64 等）下载，
# 不再依赖 PyPI MaaFw wheel。
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install --no-cache-dir \
        -r requirements.txt

# ── Stage 2: runtime ────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="Maa-Web Backend (FastAPI + MaaCore)" \
      org.opencontainers.image.authors="Maa-Web Contributors" \
      org.opencontainers.image.licenses="MIT"

# Minimal runtime-only system deps:
#   - libgomp1 / libglib2.0-0: OpenCV 依赖（引擎识别/截图）
#   - libatomic1: MaaCore 动态库依赖（libatomic.so.1，缺失会加载失败）
#   - adb: Android Debug Bridge（设备接入：网络 ADB 连局域网设备）
#   - ca-certificates: HTTPS requests (resource updates)
#   - tini: proper SIGTERM forwarding (reap children, PID1)
#   - curl/iproute2: useful ad-hoc debugging, not strictly required (size ~3MB)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libgomp1 \
        libglib2.0-0 \
        libatomic1 \
        adb \
        ca-certificates \
        tini \
        curl \
        iproute2 \
 && rm -rf /var/lib/apt/lists/* \
 && rm -rf /usr/share/doc /usr/share/man

# Copy installed deps from builder
COPY --from=builder /install /usr/local

# Verify pip-installed packages are importable from /usr/local
RUN python -c "import fastapi, uvicorn"

# ── Security: create non-root user UID/GID 1000 ────────
# 1000 matches the common default user on Synology DSM, Unraid, and most distros,
# which avoids permission headaches on named volume bind mounts (if any user swaps).
RUN groupadd --system --gid 1000 appgroup \
 && useradd  --system --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin appuser \
 && mkdir -p /home/appuser \
 && chown -R 1000:1000 /home/appuser

# ── App source ─────────────────────────────────────────
WORKDIR /app
COPY --chown=1000:1000 app /app/app

# Data mount points (must be writable by appuser even if volume is empty)
RUN mkdir -p /data/config /data/logs /data/cache /data/media /tmp \
 && chown -R 1000:1000 /data /tmp /app

# Drop privileges
USER appuser

# HOME 指向 appuser 的真实目录：adb server 启动需要 ~/.android（ADB 密钥），
# 容器默认 HOME=/root 且 /home/appuser 不存在会导致 adb 启动即失败
# （Cannot mkdir '/home/appuser/.android'）
ENV HOME=/home/appuser \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app:${PYTHONPATH}"

EXPOSE 8000

# tini → uvicorn (single process, M2+ will split worker if needed)
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--loop", "uvloop", \
     "--no-access-log", \
     "--timeout-graceful-shutdown", "25"]
