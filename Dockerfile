FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN PY03_USE_ABI3_FORWARD_COMPATIBILITY=1 pip install --no-cache-dir --prefix=/install -r requirements.txt \
    && python -m textblob.download_corpora

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
# NLTK/TextBlob looks in /usr/share/nltk_data by default if downloaded as root in stage 1
COPY app.py .
RUN useradd -m -r -u 1001 appuser && chown -R appuser /app
USER 1001
EXPOSE 8000
CMD ["python", "app.py"]