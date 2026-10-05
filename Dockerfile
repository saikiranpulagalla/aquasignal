FROM python:3.13.5-slim
WORKDIR /app
COPY requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml ./
COPY aquasignal ./aquasignal
COPY signallock ./signallock
COPY apps ./apps
COPY web_aqua ./web_aqua
COPY data/aqua ./data/aqua
COPY data/results ./data/results
ENV PYTHONUNBUFFERED=1
ENV AQUASIGNAL_ENV=production
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import httpx; r=httpx.get('http://127.0.0.1:8000/api/aqua/ready', timeout=3); r.raise_for_status()"
CMD ["python", "-m", "apps.aqua_api"]
