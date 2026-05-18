FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app.py .
RUN useradd -m -r -u 1001 appuser && chown -R appuser /app
USER 1001
RUN python -m textblob.download_corpora
EXPOSE 8000
CMD ["python", "app.py"]
