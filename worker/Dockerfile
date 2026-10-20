FROM python:3.12-slim
WORKDIR /app
# The worker runs the API's code (scan, mail, notify), so it installs the API's
# requirements, plus its own scheduler. A hand-copied subset drifted three
# times — openai, pgvector, and google-api-python-client, the last of which
# silently broke the hourly mail poll from 2026-09-22 to 2026-10-20.
COPY api/requirements.txt /tmp/api-requirements.txt
COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r /tmp/api-requirements.txt -r requirements.txt
# bring the api code in so the worker can import the scan pipeline
COPY api/ /app/api/
COPY worker/ /app/worker/
ENV PYTHONPATH=/app/api
CMD ["python", "/app/worker/scheduler.py"]
