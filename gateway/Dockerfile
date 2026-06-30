FROM python:3.12-slim

WORKDIR /app

# git krävs för minnes-vaults (commit per skrivning)
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

EXPOSE 8080
ENV MEMAIX_TRANSPORT=http
CMD ["python", "-m", "memaix_gateway.server"]
