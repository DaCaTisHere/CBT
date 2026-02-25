FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV SIMULATION_MODE=false
ENV DRY_RUN=false
ENV USE_TESTNET=false
ENV TRADING_MODE=REAL

# Expose port for healthcheck
EXPOSE 8080

# Run the bot - mode controlled by SIMULATION_MODE env variable
CMD ["python", "src/main.py"]

