# 1. Base image: a small Linux image with Python 3.12 already installed.
FROM python:3.12-slim

# 2. Python-specific environment settings.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3. Set the working directory inside the image/container.
WORKDIR /app

# 4. Install dependencies separately to benefit from Docker layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy application source code (the .env file is excluded by .dockerignore).
COPY app.py .

# 6. Create a non-root user and the writable data directory.
RUN useradd --create-home appuser && \
    mkdir -p /data && \
    chown -R appuser:appuser /app /data
USER appuser

# 7. Documentation: the app listens on 5000 inside the container.
# EXPOSE does NOT publish a host port.
EXPOSE 5000

# 8. Default process when a container starts.
CMD ["python", "app.py"]
