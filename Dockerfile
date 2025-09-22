FROM python:3.11-slim AS base

# ---- System ----------------------------------------------------
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      build-essential git curl python3-dev \
      # ── dependencies of WeasyPrint ───────────────────────────────
      libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
      libgdk-pixbuf-2.0-0 libglib2.0-0 libgirepository1.0-dev \
      libffi-dev shared-mime-info libjpeg-dev libpng-dev \
      fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

# ---- uv deps manager -----------------------------------------
RUN pip install --no-cache-dir uv

WORKDIR /app

# ─────────────────────────────────────────────────────────────────
# 1) Copy ONLY pyproject.toml (and optionally README, LICENSE…)
#    to leverage the cache of layers when the code changes
# ─────────────────────────────────────────────────────────────────
COPY pyproject.toml ./

RUN uv pip install . --system --no-cache-dir

# ─────────────────────────────────────────────────────────────────
# 2) Copy the rest of the code and THEN install dependencies
#    (this avoids `uv pip install .` from failing because there is no source)
# ─────────────────────────────────────────────────────────────────
COPY . .



# ---- Non-privileged user -----------------------------------
RUN useradd -m -u 1001 scout
RUN mkdir -p /app/media/charts && chown -R scout:scout /app/media
USER scout

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app   

EXPOSE 8000 8501 8888
CMD ["bash"]    # the docker-compose overrides this CMD