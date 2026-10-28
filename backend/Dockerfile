FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system payseal && adduser --system --ingroup payseal payseal \
    && mkdir -p /keys/organizations && chown -R payseal:payseal /keys
COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[test]"
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY tests ./tests
USER payseal
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

