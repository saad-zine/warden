FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY policies/ ./policies/
COPY incidents/ ./incidents/
COPY eval/ ./eval/

ENV AEGIS_DATA_DB=/data/aegis.db
ENV AEGIS_CHECKPOINT_DB=/data/checkpoints.db
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
