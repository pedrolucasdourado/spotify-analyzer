FROM python:3.11-slim

WORKDIR /srv

COPY api/requirements.txt ./api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

COPY api/app ./api/app
COPY data/api ./data/api

ENV SPOTIFY_DATASET=/srv/data/api/artists.parquet \
    SPOTIFY_CORS_ORIGINS=http://localhost:8080,http://127.0.0.1:8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "api", "--host", "0.0.0.0", "--port", "8000"]
