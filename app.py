"""
Real-Time Crypto Sentiment & Price Ticker
==========================================
Production-grade FastAPI service providing:
  - Live cryptocurrency prices via CoinGecko
  - RSS-driven sentiment analysis via TextBlob
  - Dynamic runtime asset registration
  - Prometheus metrics (/metrics)
  - Kubernetes health probes (/healthz)
  - Structured JSON logging (Datadog-compatible)
  - Chaos/error simulation background loop

Environment Variables:
  LOG_LEVEL                : Python log level (default: INFO)
  COINGECKO_BASE_URL       : CoinGecko API base (default: https://api.coingecko.com/api/v3)
  RSS_FEED_URL             : RSS feed to scrape (default: https://cointelegraph.com/rss)
  FETCH_INTERVAL_SECONDS   : Ingestion loop cadence in seconds (default: 30)
  CHAOS_INTERVAL_SECONDS   : Chaos loop base cadence in seconds (default: 45)
  CHAOS_PROBABILITY        : Float 0.0–1.0 chance per cycle (default: 0.15)
  HTTP_TIMEOUT_SECONDS     : Upstream HTTP call timeout (default: 10)
  PORT                     : Uvicorn bind port (default: 8000)
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Configuration — all values sourced from environment variables
# ---------------------------------------------------------------------------

LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()
COINGECKO_BASE_URL: str = os.environ.get(
    "COINGECKO_BASE_URL", "https://api.coingecko.com/api/v3"
)
RSS_FEED_URL: str = os.environ.get(
    "RSS_FEED_URL", "https://cointelegraph.com/rss"
)
FETCH_INTERVAL_SECONDS: int = int(os.environ.get("FETCH_INTERVAL_SECONDS", "30"))
CHAOS_INTERVAL_SECONDS: int = int(os.environ.get("CHAOS_INTERVAL_SECONDS", "45"))
CHAOS_PROBABILITY: float = float(os.environ.get("CHAOS_PROBABILITY", "0.15"))
HTTP_TIMEOUT_SECONDS: int = int(os.environ.get("HTTP_TIMEOUT_SECONDS", "10"))
PORT: int = int(os.environ.get("PORT", "8000"))


# ---------------------------------------------------------------------------
# Structured JSON Logger — Datadog-compatible stdout format
# ---------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    """
    Emits every log record as a single-line JSON object. All standard fields
    (timestamp, level, logger, message) are always present. Extra context keys
    injected via the `extra={}` kwarg are merged in automatically.
    """

    # Keys promoted to top-level fields if present in extra
    _CONTEXT_KEYS: tuple[str, ...] = (
        "ticker",
        "endpoint",
        "latency_ms",
        "chaos_event",
        "http_status",
    )

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in self._CONTEXT_KEYS:
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def _build_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
    logger.propagate = False
    return logger


log = _build_logger("crypto_ticker")


