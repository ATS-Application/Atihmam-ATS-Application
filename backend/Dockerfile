# Stage 1: Build
FROM python:3.11-slim AS builder
WORKDIR /app
RUN pip install uv
COPY requirements.txt .
# Install into a virtual environment
RUN uv venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN uv pip install -r requirements.txt

# Stage 2: Final
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY . .

# Correctly binding to the port assigned by the cloud provider
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]