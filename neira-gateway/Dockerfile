# Neira Gateway — relay tipis PC (otak) ↔ klien (HP/browser)
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway/ ./gateway/
COPY web/ ./web/

ENV GATEWAY_HOST=0.0.0.0 \
    GATEWAY_PORT=8765 \
    GATEWAY_DATA_DIR=/app/data

VOLUME ["/app/data"]
EXPOSE 8765

CMD ["uvicorn", "gateway.server:app", "--host", "0.0.0.0", "--port", "8765", "--log-level", "warning"]
