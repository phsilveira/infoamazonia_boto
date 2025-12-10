FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir pip -U && \
    pip install --no-cache-dir build && \
    pip install --no-cache-dir .

# Copy project files
COPY . .

# Expose port
EXPOSE 8000

# Run application
CMD ["python", "main.py"]