FROM python:3.11-slim

# Install uv by copying it from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy requirements and install them globally
COPY requirements.txt .
RUN uv pip install --system --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Set the command to run your application
# Replace your current CMD with this:
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
