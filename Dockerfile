FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (gcc for potential compilation)
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Application Code
# We assume the context is /opt/cryptobot and it contains folders like antigravity/
COPY . .

# Environment Variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default Command (Overridden by docker-compose)
CMD ["python", "main.py"]
