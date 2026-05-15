FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic[email]>=2.9" \
    "pydantic-settings>=2.6" "PyJWT[crypto]>=2.9" "httpx>=0.27" \
    "structlog>=24.4" "sse-starlette>=2.1"
COPY src ./src
COPY .env.example ./.env.example
RUN useradd -u 10001 -m app && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
