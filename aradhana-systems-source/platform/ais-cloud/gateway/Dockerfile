FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY ais-cloud/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ais-cloud/gateway/app ./app
COPY core/ais.registry.json ./registry/ais.registry.json
RUN useradd --create-home --uid 10001 ais && mkdir -p /var/lib/ais && chown -R ais:ais /app /var/lib/ais
USER ais
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
