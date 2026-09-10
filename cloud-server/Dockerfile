FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    TMPDIR=/tmp \
    PORT=8000 \
    QR_DATA_DIR=/var/lib/aradhana-print

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN useradd --system --create-home --uid 10001 aradhana \
    && mkdir -p /var/lib/aradhana-print \
    && chown -R aradhana:aradhana /app /var/lib/aradhana-print
USER aradhana

EXPOSE 8000
CMD ["gunicorn", "--workers", "2", "--threads", "4", "--timeout", "120", "--bind", "0.0.0.0:8000", "app:app"]
