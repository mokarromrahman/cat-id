FROM python:3.14-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 HF_HOME=/app/hf_cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY embed.py train.py app.py sorter_core.py db.py vet_api.py start.py replay_db_failed.py alembic.ini ./
COPY migrations ./migrations
COPY ui ./ui
COPY img_src ./img_src
EXPOSE 8000
# start.py waits up to 30 s for Postgres, runs the migrations, then starts uvicorn either way.
CMD ["python", "start.py"]
