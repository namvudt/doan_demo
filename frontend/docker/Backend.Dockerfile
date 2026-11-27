FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHON_DOTENV_DISABLED=1 API_CATALOG_MEDIA_DIR=/app/catalog-media
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY api ./api
COPY agents ./agents
COPY core ./core
COPY workflow ./workflow
COPY utils ./utils
COPY config ./config
COPY migrations ./migrations
COPY samples ./samples
COPY frontend/public/heritages ./catalog-media
COPY scripts ./scripts
COPY docs/langgraph.mmd ./docs/langgraph.mmd
COPY alembic.ini ./
ARG HERITAGE_BUILD_REVISION=development
ENV HERITAGE_BUILD_REVISION=${HERITAGE_BUILD_REVISION}
LABEL org.opencontainers.image.revision=${HERITAGE_BUILD_REVISION}
RUN useradd --uid 10001 --create-home heritage && mkdir -p /app/data && chown -R heritage:heritage /app
USER heritage
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
