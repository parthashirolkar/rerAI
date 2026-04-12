FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/tmp/uv-cache \
    PATH="/home/app/.local/bin:${PATH}"

RUN useradd --create-home --shell /bin/bash app

COPY --from=ghcr.io/astral-sh/uv:0.7.21 /uv /home/app/.local/bin/uv

USER app
WORKDIR /app

COPY --chown=app:app pyproject.toml uv.lock README.md app.py ./
COPY --chown=app:app src ./src

RUN /home/app/.local/bin/uv sync --frozen --no-dev

EXPOSE 8000

CMD ["/home/app/.local/bin/uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
