FROM python:3.12-slim
WORKDIR /app
COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# bring the api code in so the worker can import the scan pipeline
COPY api/ /app/api/
COPY worker/ /app/worker/
ENV PYTHONPATH=/app/api
CMD ["python", "/app/worker/scheduler.py"]
