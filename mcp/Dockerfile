# Treadwell AI News Feed — custom connector (remote MCP). Single small service,
# no database: it reads the live feed over HTTPS. Isolated from the feed container.
FROM python:3.12-slim

WORKDIR /app

# Install deps first (better layer caching), then the package.
COPY pyproject.toml ./
COPY newsfeed_mcp ./newsfeed_mcp
RUN pip install --no-cache-dir .

# Defaults; real values come from the env_file at runtime.
ENV MCP_HOST=0.0.0.0 \
    MCP_PORT=8894 \
    MCP_TRANSPORT=http \
    NEWSFEED_BASE_URL=https://newsfeed.wetreadwell.com

EXPOSE 8894

# Lightweight liveness check against the connector's own health route.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('MCP_PORT','8894')+'/healthz', timeout=4)" || exit 1

CMD ["newsfeed-mcp"]
