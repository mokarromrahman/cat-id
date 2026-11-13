FROM python:3.14-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 HF_HOME=/app/hf_cache
# Time zones come from the pip `tzdata` package (in requirements.txt, latest on each build),
# not the base image's files: an empty PYTHONTZPATH makes zoneinfo skip the system copy.
# Edmonton's rules changed recently (UTC-6 all year from Nov 2026, tzdata 2026c), and an old
# copy would put events an hour off.
ENV PYTHONTZPATH=
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY embed.py train.py app.py sorter_core.py db.py vet_api.py events_api.py start.py replay_db_failed.py alembic.ini ./
COPY migrations ./migrations
COPY ui ./ui
COPY img_src ./img_src
EXPOSE 8000
# start.py waits up to 30 s for Postgres, runs the migrations, then starts uvicorn either way.
CMD ["python", "start.py"]
