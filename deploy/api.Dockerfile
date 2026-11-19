# platform-api for the single-server deployment (deploy/README.md). Build context: ../backend
#
# Unlike backend/Dockerfile, this image also carries alembic.ini and scripts/, so the migrations, the seed
# and the MaaS check run inside the container and the server needs no Python environment of its own.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /srv
COPY pyproject.toml alembic.ini ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY scripts ./scripts
RUN useradd --system --uid 10001 --no-create-home amc
USER amc
EXPOSE 8000
# One process only: the local sign-in key lives in this process (app/core/dev_auth.py), so a second
# worker process would reject the tokens the first one signed.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-server-header"]
