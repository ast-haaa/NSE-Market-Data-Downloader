FROM python:3.12-slim

LABEL maintainer="NSE Market Data Downloader"
LABEL description="Automated NSE India market data downloader"

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py ./
COPY tests/ ./tests/
COPY web/ ./web/

# Create output and log directories
RUN mkdir -p /app/output /app/logs

# Default: download all datasets
ENTRYPOINT ["python", "main.py"]
CMD ["--output-dir", "/app/output"]
