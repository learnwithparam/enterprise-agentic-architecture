FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.3 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY policies ./policies
COPY world ./world
COPY migrations ./migrations
RUN uv sync --frozen --no-dev --no-group deploy
ENV PATH="/app/.venv/bin:$PATH"
USER 10001
EXPOSE 8765
CMD ["uvicorn", "hcpagents.api:app", "--host", "0.0.0.0", "--port", "8765"]
