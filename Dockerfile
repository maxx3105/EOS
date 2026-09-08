# syntax=docker/dockerfile:1.7
# Dockerfile

# Support both Home Assistant builds and standalone builds.
# Only Debian based images are supported (no Alpine).
ARG BUILD_FROM
ARG PYTHON_VERSION=3.13.15

# Builder and runtime share the same base so the copied virtualenv is ABI-safe.
# If BUILD_FROM is set (Home Assistant), use it; otherwise use python-slim.
FROM ${BUILD_FROM:-python:${PYTHON_VERSION}-slim} AS builder

# uv: pinned, copied as a static binary (no extra Python packages installed).
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /opt/eos

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    gcc g++ gfortran \
    libopenblas-dev liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src/ ./src
COPY scripts/get_version.py ./scripts/get_version.py
RUN python scripts/get_version.py > version.txt

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM ${BUILD_FROM:-python:${PYTHON_VERSION}-slim} AS runtime

ARG BUILD_VERSION=dev

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="addon" \
    io.hass.arch="aarch64|amd64" \
    source="https://github.com/maxx3105/EOS" \
    org.opencontainers.image.source="https://github.com/maxx3105/EOS" \
    org.opencontainers.image.licenses="Apache-2.0" \
    org.opencontainers.image.title="EOS for Victron Cerbo GX" \
    org.opencontainers.image.description="EOS PV forecast with Victron Cerbo GX support for Synology Container Manager"

ENV EOS_DIR="/opt/eos"
ENV EOS_DATA_DIR="/data"
ENV EOS_CACHE_DIR="${EOS_DATA_DIR}/cache"
ENV EOS_HEALTHCHECK_PORT_FILE="${EOS_CACHE_DIR}/eos-healthcheck-port"
ENV EOS_OUTPUT_DIR="${EOS_DATA_DIR}/output"
ENV EOS_CONFIG_DIR="${EOS_DATA_DIR}/config"
ENV MPLCONFIGDIR="${EOS_DATA_DIR}/mplconfigdir"

# Standalone defaults. These make the image usable directly from Synology
# Container Manager without a Compose file or extra environment variables.
ENV EOS_SERVER__HOST="0.0.0.0"
ENV EOS_SERVER__PORT="8503"
ENV EOS_SERVER__EOSDASH_HOST="0.0.0.0"
ENV EOS_SERVER__EOSDASH_PORT="8504"
ENV EOS_SERVER__EOSDASH_SESSKEY="eos-victron-local-session"

ENV OPENBLAS_NUM_THREADS=1
ENV OMP_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV PIP_PROGRESS_BAR=off
ENV PIP_NO_COLOR=1

ENV LANG=C.UTF-8
ENV VENV_PATH=/opt/venv
ENV PATH="$VENV_PATH/bin:$PATH"

WORKDIR ${EOS_DIR}

RUN apt-get update && apt-get install -y --no-install-recommends \
    adduser python3 libopenblas0 liblapack3 \
    && adduser --system --group --no-create-home eos \
    && mkdir -p "${EOS_DATA_DIR}" "${EOS_CACHE_DIR}" "${EOS_OUTPUT_DIR}" "${EOS_CONFIG_DIR}" "${MPLCONFIGDIR}" \
    && chown -R eos:eos "${EOS_DATA_DIR}" \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY src/ ./src

ENTRYPOINT []

EXPOSE 8503
EXPOSE 8504

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-m", "akkudoktoreos.server.container_healthcheck"]

CMD ["python", "-m", "akkudoktoreos.server.eos", "--host", "0.0.0.0", "--run_as_user", "eos"]

VOLUME ["${EOS_DATA_DIR}"]
