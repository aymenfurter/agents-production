# Stage 1: builder
FROM python:3.12-slim AS builder

ENV VENV=/opt/venv
RUN python -m venv $VENV
ENV PATH="$VENV/bin:$PATH"

WORKDIR /app

# System deps for building common wheels
# If you keep "psycopg2", include libpq-dev and pkg-config
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    pkg-config \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# If you switched to "psycopg2-binary", you can drop libpq-dev above
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: runtime
FROM python:3.12-slim

ENV VENV=/opt/venv
ENV PATH="$VENV/bin:$PATH"

WORKDIR /app

# Runtime libs only
# If you keep "psycopg2", you need libpq5 at runtime
RUN apt-get update && apt-get install -y \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv

# App code
COPY . .

EXPOSE 7860
ENV GRADIO_SERVER_NAME="0.0.0.0"
ENV GRADIO_SERVER_PORT="7860"

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:7860/ || exit 1

CMD ["python", "main.py"]
