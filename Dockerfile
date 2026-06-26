# syntax=docker/dockerfile:1.6
FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema mínimas (curl es sólo para el healthcheck).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar deps Python en su propia capa para cachearla entre rebuilds.
# Si existe requirements.lock (pip freeze de una build conocida-buena), se usa
# ese: builds reproducibles, sin sorpresas de versiones nuevas (premortem #3, R8).
# Para generarlo/actualizarlo: ver RUNBOOK-OPERACION.md.
COPY requirements.txt requirements.lock* ./
RUN if [ -f requirements.lock ]; then \
        pip install --no-cache-dir -r requirements.lock; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

# Código de la app. tests/ no se copia porque no corre en producción.
COPY app.py ./
COPY core/ ./core/
COPY ui/ ./ui/
COPY scripts/ ./scripts/
# Tema visual de Streamlit (paleta, fuente, etc.).
COPY .streamlit/ ./.streamlit/
# Assets visuales (logo, favicon).
COPY assets/ ./assets/

# Entrypoint que siembra la base la primera vez (si hay seed).
# El sed saca cualquier \r (CRLF de Windows) que rompería el shebang en Linux.
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN sed -i 's/\r$//' /app/docker-entrypoint.sh && chmod +x /app/docker-entrypoint.sh

# El volumen /app/data se monta para persistir la DB y los backups.
RUN mkdir -p /app/data/backups

# Streamlit en modo producción.
ENV STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_RUN_ON_SAVE=false \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=true \
    DB_PATH=/app/data/finanzas.db \
    PYTHONUNBUFFERED=1

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD ["/app/docker-entrypoint.sh"]
