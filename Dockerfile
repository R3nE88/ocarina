FROM python:3.13-slim
WORKDIR /app/server
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ .
COPY site/ /app/site/
RUN useradd --system app
USER app
EXPOSE 8000
# proxy headers: the client IP (used for rate limits) comes from Traefik in Dokploy
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
