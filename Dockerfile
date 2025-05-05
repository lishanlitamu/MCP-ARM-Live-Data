# Dockerfile
FROM python:3.12-slim-bookworm

# Install uv using the official distroless image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory in the container
WORKDIR /app

# Copy project definition (pyproject.toml) and lock file (if available)
COPY pyproject.toml ./
COPY uv.lock ./

# Install dependencies using uv sync.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# Copy the application code into the container
COPY src/arm-live-data.py .

# Install the project itself using uv sync.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# Copy the .env file into the container
COPY .env .

# Define the command to run the application using 'uv run'
CMD ["uv", "run", "arm-live-data.py"]