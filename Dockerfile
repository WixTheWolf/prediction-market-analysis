FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock* README.md ./
RUN uv sync --frozen --no-dev

COPY src ./src
COPY docs ./docs
RUN mkdir -p /app/output/live

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"

CMD ["uv", "run", "python", "-m", "src.agent.service"]
