# Python 3.11 is the development interpreter used for this backend.
FROM python:3.11-slim-bookworm AS base
WORKDIR /app

COPY requirements/ ./requirements/
RUN pip install --no-cache-dir -r requirements/base.txt -r requirements/a-geo.txt -r requirements/b-app.txt
COPY app/ ./app/

FROM base AS test
COPY tests/b/ ./tests/b/
RUN python -m pytest tests/b

FROM base AS runtime
RUN chown nobody /app
USER nobody
# The backend API port is documented in README.md §5.
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
