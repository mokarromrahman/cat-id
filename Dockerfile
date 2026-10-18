FROM python:3.14-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 HF_HOME=/app/hf_cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY embed.py train.py app.py sorter_core.py ./
COPY ui ./ui
COPY img_src ./img_src
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
