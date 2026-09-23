FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    TMPDIR=/tmp \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN useradd --system --create-home --uid 10003 ambicdigital \
    && mkdir -p /var/lib/aradhana-payment-notifier \
    && chown -R ambicdigital:ambicdigital /app /var/lib/aradhana-payment-notifier
USER ambicdigital

EXPOSE 8000
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--timeout", "120", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "app:app"]
