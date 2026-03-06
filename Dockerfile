FROM python:3.10-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV SIMULATION_MODE=false \
    DRY_RUN=false \
    USE_TESTNET=false \
    TRADING_MODE=REAL

EXPOSE 8080

CMD ["python", "src/main.py"]

