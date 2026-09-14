FROM python:3.12-slim

WORKDIR /app

# Install libvips for Pillow image processing
RUN apt-get update && apt-get install -y \
    libvips \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create local fallback dirs (used when /data volume isn't mounted)
RUN mkdir -p /data/uploads /data/thumbs

EXPOSE 8080

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8080", \
     "--timeout", "120", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "app:app"]
