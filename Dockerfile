FROM python:3.10-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV SIMULATION_MODE=true \
    DRY_RUN=false \
    USE_TESTNET=false \
    TRADING_MODE=SIMULATION

EXPOSE 8080

CMD ["python", "src/main.py"]

