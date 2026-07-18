FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install uv itself (grab the static binary, no pip bootstrap needed)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY . .

EXPOSE 5003

CMD ["python", "app.py"]