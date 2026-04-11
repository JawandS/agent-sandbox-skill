FROM python:3.11-slim

WORKDIR /app

COPY demo/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source and the infra template (needed for CFN stack creation)
COPY demo/ .
COPY infra/sandbox_template.yaml infra/sandbox_template.yaml

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
