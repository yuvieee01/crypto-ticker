FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt \
    && python -m textblob.download_corpora

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app.py .
RUN useradd -r -u 1001 appuser && chown -R appuser /app
USER 1001
EXPOSE 8000
CMD ["python", "app.py"]