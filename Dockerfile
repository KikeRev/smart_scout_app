FROM python:3.11-slim AS base

# ---- Sistema ----------------------------------------------------
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      build-essential git curl python3-dev \
      # ── dependencias de WeasyPrint ───────────────────────────────
      libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
      libgdk-pixbuf-2.0-0 libglib2.0-0 libgirepository1.0-dev \
      libffi-dev shared-mime-info libjpeg-dev libpng-dev \
      fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

# ---- Gestor de deps uv -----------------------------------------
RUN pip install --no-cache-dir uv

WORKDIR /app

# ─────────────────────────────────────────────────────────────────
# 1) Copiamos SOLO pyproject.toml (y opcionalmente README, LICENSE…)
#    para aprovechar la cache de capas cuando cambie el código
# ─────────────────────────────────────────────────────────────────
COPY pyproject.toml ./

RUN uv pip install . --system --no-cache-dir

# ─────────────────────────────────────────────────────────────────
# 2) Copiamos el resto del código y ENT0NCES instalamos dependencias
#    (esto evita que `uv pip install .` falle porque aún no hay fuente)
# ─────────────────────────────────────────────────────────────────
COPY . .



# ---- Usuario sin privilegios -----------------------------------
RUN useradd -m -u 1001 scout
RUN mkdir -p /app/media/charts && chown -R scout:scout /app/media
USER scout

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app   

EXPOSE 8000 8501 8888
CMD ["bash"]    # el docker-compose sobrescribe este CMD