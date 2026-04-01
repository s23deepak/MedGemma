# ── Base image ────────────────────────────────────────────────────────────────
# CUDA 12.4 + cuDNN dev headers required by vLLM kernel compilation
FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04

# ── Build args ────────────────────────────────────────────────────────────────
ARG PYTHON_VERSION=3.11
ARG UV_VERSION=0.4.30

# ── Environment ───────────────────────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # uv: keep venv inside project so layers cache cleanly
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    # vLLM: disable telemetry
    VLLM_USAGE_STATS_ENABLED=0 \
    # HuggingFace cache — bind-mounted at runtime so models survive restarts
    HF_HOME=/cache/huggingface \
    # Default to production mode on the L4
    VLLM_ENV=production

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        # Python 3.11
        software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update && apt-get install -y --no-install-recommends \
        python${PYTHON_VERSION} \
        python${PYTHON_VERSION}-dev \
        python${PYTHON_VERSION}-venv \
        python3-pip \
        # Audio (sounddevice / MedASR)
        libsndfile1 \
        portaudio19-dev \
        ffmpeg \
        # General build tools
        curl \
        git \
        build-essential \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Make python3.11 the default python3
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python${PYTHON_VERSION} 1 \
    && update-alternatives --set python3 /usr/bin/python${PYTHON_VERSION}

# ── Install uv ────────────────────────────────────────────────────────────────
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# ── Dependency installation ───────────────────────────────────────────────────
WORKDIR /app

# Copy only dependency manifests first — rebuild this layer only when deps change
COPY pyproject.toml uv.lock ./

# Install all dependencies including vllm and rag extras
# --no-dev skips test/lint tools; --frozen respects the lockfile exactly
RUN uv sync \
        --extra vllm \
        --extra rag \
        --no-dev \
        --frozen \
        --python python${PYTHON_VERSION}

# ── Application code ──────────────────────────────────────────────────────────
COPY . .

# ── Ports ─────────────────────────────────────────────────────────────────────
# 8000 — FastAPI / uvicorn
# 8001 — Prometheus metrics (MetricsCollector.start_prometheus_server)
EXPOSE 8000 8001

# ── Healthcheck ───────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Entrypoint ────────────────────────────────────────────────────────────────
# workers=1 is intentional — vLLM manages its own async concurrency internally.
# Multiple workers would each load a full model copy, exhausting VRAM.
CMD ["uv", "run", "uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--log-level", "info"]
