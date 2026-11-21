# Python 3.11 is the development interpreter used for this backend.
FROM python:3.11-slim-bookworm AS base
WORKDIR /app

# Debian wheel dependencies documented at https://doc.courtbouillon.org/weasyprint/stable/first_steps.html.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ ./requirements/
RUN pip install --no-cache-dir -r requirements/base.txt -r requirements/a-geo.txt -r requirements/b-app.txt
COPY app/ ./app/
COPY config/ ./config/

FROM base AS test
COPY tests/b/ ./tests/b/
COPY tests/fixtures/sample_report.json ./tests/fixtures/sample_report.json
RUN python -m pytest tests/b

FROM base AS runtime
RUN mkdir /app/data && chown nobody /app /app/data
USER nobody
# The backend API port is documented in README.md §5.
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
