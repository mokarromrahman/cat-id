FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 HF_HOME=/app/hf_cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY embed.py train.py app.py ./
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
