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

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import feedparser
import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    REGISTRY,
    generate_latest,
)
from pydantic import BaseModel, field_validator
from textblob import TextBlob

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


# ---------------------------------------------------------------------------
# Prometheus Metrics Registry
# ---------------------------------------------------------------------------

PRICE_GAUGE = Gauge(
    "crypto_price_usd",
    "Current cryptocurrency price in USD",
    labelnames=["ticker"],
)

SENTIMENT_GAUGE = Gauge(
    "crypto_sentiment_score",
    "TextBlob polarity score for latest matching RSS headlines (-1.0 to 1.0)",
    labelnames=["ticker"],
)

API_REQUESTS_COUNTER = Counter(
    "crypto_api_requests_total",
    "Total successful API calls to upstream endpoints",
    labelnames=["endpoint", "status"],
)

API_ERRORS_COUNTER = Counter(
    "crypto_api_errors_total",
    "Total upstream API errors — both real network failures and simulated chaos",
    labelnames=["endpoint", "error_type"],
)

SCRAPE_LATENCY_HISTOGRAM = Histogram(
    "crypto_scrape_latency_seconds",
    "Wall-clock duration of a full ingestion loop cycle",
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0),
)

# Define the latency histogram with custom duration buckets (in seconds)
API_LATENCY_HISTOGRAM = Histogram(
    'crypto_api_request_duration_seconds',
    'Time spent waiting for upstream API and RSS feed responses',
    labelnames=['endpoint'],
    buckets=(0.5, 1.0, 2.0, 3.5, 5.0, 7.5, float("inf"))
)

# ---------------------------------------------------------------------------
# Domain Models
# ---------------------------------------------------------------------------

@dataclass
class CryptoAsset:
    """Mutable state container for a single tracked cryptocurrency."""
    coingecko_id: str
    keywords: list[str]
    price_usd: float = 0.0
    sentiment_score: float = 0.0
    last_updated: str = ""


class AddTickerRequest(BaseModel):
    """Payload for POST /api/ticker."""
    id: str
    keywords: list[str]

    @field_validator("id")
    @classmethod
    def _normalize_id(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("Coin ID must be a non-empty string.")
        return v

    @field_validator("keywords")
    @classmethod
    def _validate_keywords(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one keyword is required.")
        return [kw.strip() for kw in v if kw.strip()]


# ---------------------------------------------------------------------------
# In-Memory State — Protected by asyncio (single-threaded event loop)
# ---------------------------------------------------------------------------

TRACKED_ASSETS: dict[str, CryptoAsset] = {
    "bitcoin":  CryptoAsset(coingecko_id="bitcoin",  keywords=["Bitcoin",  "BTC"]),
    "ethereum": CryptoAsset(coingecko_id="ethereum", keywords=["Ethereum", "ETH"]),
    "solana":   CryptoAsset(coingecko_id="solana",   keywords=["Solana",   "SOL"]),
}


# ---------------------------------------------------------------------------
# Chaos Event Catalogue
# ---------------------------------------------------------------------------

_CHAOS_CATALOGUE: list[dict[str, Any]] = [
    {
        "error_type": "rate_limit",
        "http_code":  429,
        "message":    "Simulated HTTP 429 Rate Limit — CoinGecko upstream throttled",
    },
    {
        "error_type": "gateway_timeout",
        "http_code":  504,
        "message":    "Simulated HTTP 504 Gateway Timeout — upstream mesh unresponsive",
    },
]


async def _maybe_inject_chaos(endpoint: str) -> None:
    """
    Probabilistically fires a chaos event for `endpoint`.

    On trigger:
      1. Emits a CRITICAL JSON log line (visible to Datadog/alertmanager).
      2. Increments `crypto_api_errors_total` with the chaos error type.
      3. Sleeps 3–5 seconds to simulate degraded network conditions.
    """
    if random.random() >= CHAOS_PROBABILITY:
        return

    event = random.choice(_CHAOS_CATALOGUE)
    latency_s: float = random.uniform(3.0, 5.0)

    log.critical(
        event["message"],
        extra={
            "chaos_event":  event["error_type"],
            "endpoint":     endpoint,
            "http_status":  event["http_code"],
            "latency_ms":   round(latency_s * 1000, 2),
        },
    )
    API_ERRORS_COUNTER.labels(
        endpoint=endpoint,
        error_type=event["error_type"],
    ).inc()

    await asyncio.sleep(latency_s)


# ---------------------------------------------------------------------------
# Upstream Data Helpers
# ---------------------------------------------------------------------------

async def _fetch_prices(client: httpx.AsyncClient) -> dict[str, float]:
    """
    GETs USD prices for all currently tracked assets from CoinGecko.

    Returns:
        Mapping of {coingecko_id: price_usd}.

    Raises:
        httpx.HTTPStatusError: On 4xx/5xx HTTP responses.
        httpx.RequestError:    On connection/timeout failures.
        KeyError:              If the response JSON is missing expected keys.
    """
    ids_param = ",".join(TRACKED_ASSETS.keys())
    url = f"{COINGECKO_BASE_URL}/simple/price"
    params: dict[str, str] = {"ids": ids_param, "vs_currencies": "usd"}

    endpoint_name = "coingecko_price"

    # Start the timer bucket before entering the execution logic
    with API_LATENCY_HISTOGRAM.labels(endpoint=endpoint_name).time():
        
        # 1. Fires potential chaos (adds 3-5s sleep if probability triggers)
        await _maybe_inject_chaos(endpoint=endpoint_name)

        # 2. Executes the actual network request
        response = await client.get(url, params=params, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()

    # Timer stops clean right here when exiting the 'with' block
    API_REQUESTS_COUNTER.labels(endpoint=endpoint_name, status="success").inc()

    raw: dict[str, Any] = response.json()
    return {
        coin_id: float(payload["usd"])
        for coin_id, payload in raw.items()
        if isinstance(payload, dict) and "usd" in payload
    }


def _parse_rss_headlines() -> list[str]:
    """
    Synchronously fetches and parses the configured RSS feed.
    Designed to run inside `asyncio.get_running_loop().run_in_executor()`
    to avoid blocking the event loop.

    Returns:
        List of headline strings (entry titles). Empty list on parse failure.
    """
    feed = feedparser.parse(RSS_FEED_URL)
    return [
        entry.title
        for entry in feed.entries
        if hasattr(entry, "title") and entry.title
    ]


def _calculate_sentiment(headlines: list[str], keywords: list[str]) -> float:
    """
    Filters `headlines` by `keywords`, computes mean TextBlob polarity.

    Returns:
        Float in [-1.0, 1.0]. Returns 0.0 (neutral) if no headline matches.
    """
    matched: list[str] = [
        h for h in headlines
        if any(kw.lower() in h.lower() for kw in keywords)
    ]
    if not matched:
        return 0.0

    total_polarity = sum(TextBlob(h).sentiment.polarity for h in matched)
    return round(total_polarity / len(matched), 4)


# ---------------------------------------------------------------------------
# Background Loop 1 — Data Ingestion & Sentiment (every FETCH_INTERVAL_SECONDS)
# ---------------------------------------------------------------------------

async def _ingestion_loop() -> None:
    """
    Main data pipeline loop. Runs indefinitely, sleeping between cycles.

    Per cycle:
      - Fetches live USD prices from CoinGecko.
      - Scrapes RSS headlines (in thread executor).
      - Calculates per-asset sentiment from filtered headlines.
      - Updates in-memory TRACKED_ASSETS state.
      - Pushes values to Prometheus Gauges.
      - Records loop duration in SCRAPE_LATENCY_HISTOGRAM.

    All sub-operations are independently wrapped in try/except so that
    a single upstream failure never terminates the loop or crashes the process.
    """
    log.info("Ingestion loop starting — interval=%ds", FETCH_INTERVAL_SECONDS)

    async with httpx.AsyncClient() as client:
        while True:
            loop_start = time.monotonic()
            log.info("Ingestion cycle begin")

            # ── 1. Price Fetch ────────────────────────────────────────────────
            prices: dict[str, float] = {}
            try:
                prices = await _fetch_prices(client)
                log.info("Fetched prices for %d assets", len(prices))
            except httpx.HTTPStatusError as exc:
                log.error(
                    "CoinGecko returned HTTP %d",
                    exc.response.status_code,
                    extra={"endpoint": "coingecko_price", "http_status": exc.response.status_code},
                )
                API_ERRORS_COUNTER.labels(
                    endpoint="coingecko_price",
                    error_type=f"http_{exc.response.status_code}",
                ).inc()
            except httpx.TimeoutException as exc:
                log.error(
                    "CoinGecko request timed out: %s",
                    str(exc),
                    extra={"endpoint": "coingecko_price"},
                )
                API_ERRORS_COUNTER.labels(
                    endpoint="coingecko_price",
                    error_type="timeout",
                ).inc()
            except httpx.RequestError as exc:
                log.error(
                    "CoinGecko network error: %s",
                    str(exc),
                    extra={"endpoint": "coingecko_price"},
                )
                API_ERRORS_COUNTER.labels(
                    endpoint="coingecko_price",
                    error_type="network_error",
                ).inc()

            # ── 2. RSS Headline Fetch (thread executor) ───────────────────────
            headlines: list[str] = []
            try:
                await _maybe_inject_chaos(endpoint="rss_feed")
                loop = asyncio.get_running_loop()
                headlines = await loop.run_in_executor(None, _parse_rss_headlines)
                API_REQUESTS_COUNTER.labels(endpoint="rss_feed", status="success").inc()
                log.info("Fetched %d RSS headlines", len(headlines))
            except Exception as exc:  # feedparser can raise broad exceptions
                log.error(
                    "RSS feed parse error: %s",
                    str(exc),
                    extra={"endpoint": "rss_feed"},
                    exc_info=True,
                )
                API_ERRORS_COUNTER.labels(
                    endpoint="rss_feed",
                    error_type="parse_error",
                ).inc()

            # ── 3. Per-Asset State Update ─────────────────────────────────────
            now_iso = datetime.now(tz=timezone.utc).isoformat()

            for asset_id, asset in list(TRACKED_ASSETS.items()):
                try:
                    if asset_id in prices:
                        asset.price_usd = prices[asset_id]
                        PRICE_GAUGE.labels(ticker=asset_id).set(asset.price_usd)

                    sentiment = _calculate_sentiment(headlines, asset.keywords)
                    asset.sentiment_score = sentiment
                    SENTIMENT_GAUGE.labels(ticker=asset_id).set(sentiment)

                    asset.last_updated = now_iso

                    log.info(
                        "Asset updated: %s price=$%.2f sentiment=%.4f",
                        asset_id,
                        asset.price_usd,
                        asset.sentiment_score,
                        extra={"ticker": asset_id},
                    )
                except (KeyError, ValueError, TypeError, AttributeError) as exc:
                    log.error(
                        "State update failed for asset '%s': %s",
                        asset_id,
                        str(exc),
                        extra={"ticker": asset_id},
                        exc_info=True,
                    )

            # ── 4. Observe loop duration ──────────────────────────────────────
            elapsed = time.monotonic() - loop_start
            SCRAPE_LATENCY_HISTOGRAM.observe(elapsed)
            log.info(
                "Ingestion cycle complete",
                extra={"latency_ms": round(elapsed * 1000, 2)},
            )

            await asyncio.sleep(FETCH_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# Background Loop 2 — Chaos & Error Simulation (every CHAOS_INTERVAL_SECONDS ± jitter)
# ---------------------------------------------------------------------------

async def _chaos_loop() -> None:
    """
    Standalone chaos simulation loop, independent of the ingestion pipeline.

    Each cycle fires _maybe_inject_chaos() against a synthetic endpoint label
    ('chaos_loop'). Jitter of 0–15 seconds prevents clock-aligned bursts
    with the ingestion loop.
    """
    log.info(
        "Chaos loop starting — base_interval=%ds probability=%.0f%%",
        CHAOS_INTERVAL_SECONDS,
        CHAOS_PROBABILITY * 100,
    )
    while True:
        jitter_s = random.uniform(0.0, 15.0)
        await asyncio.sleep(CHAOS_INTERVAL_SECONDS + jitter_s)

        if random.random() < CHAOS_PROBABILITY:
            event = random.choice(_CHAOS_CATALOGUE)
            latency_s = random.uniform(3.0, 5.0)
            log.critical(
                "[CHAOS] Standalone failure event: %s",
                event["message"],
                extra={
                    "chaos_event":  event["error_type"],
                    "endpoint":     "chaos_loop",
                    "http_status":  event["http_code"],
                    "latency_ms":   round(latency_s * 1000, 2),
                },
            )
            API_ERRORS_COUNTER.labels(
                endpoint="chaos_loop",
                error_type=event["error_type"],
            ).inc()
            await asyncio.sleep(latency_s)
        else:
            log.info("Chaos loop cycle complete — no event triggered")


# ---------------------------------------------------------------------------
# FastAPI Application — Lifespan manages background task lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Manages background task lifecycle tied to FastAPI's startup/shutdown.
    Both tasks are cancelled and awaited cleanly on SIGTERM/SIGINT.
    """
    log.info(
        "Application starting — port=%d fetch_interval=%ds chaos_interval=%ds",
        PORT,
        FETCH_INTERVAL_SECONDS,
        CHAOS_INTERVAL_SECONDS,
    )
    ingestion_task = asyncio.create_task(
        _ingestion_loop(), name="ingestion_loop"
    )
    chaos_task = asyncio.create_task(
        _chaos_loop(), name="chaos_loop"
    )
    try:
        yield
    finally:
        log.info("Application shutting down — cancelling background tasks")
        ingestion_task.cancel()
        chaos_task.cancel()
        await asyncio.gather(ingestion_task, chaos_task, return_exceptions=True)
        log.info("Background tasks stopped — shutdown complete")


app = FastAPI(
    title="Crypto Sentiment & Price Ticker",
    description=(
        "Real-time cryptocurrency price and sentiment tracker. "
        "Exposes Prometheus metrics, structured JSON logs, and a dynamic ticker registry."
    ),
    version="1.0.0",
    lifespan=_lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ---------------------------------------------------------------------------
# Ops Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/healthz",
    tags=["ops"],
    summary="Kubernetes liveness / readiness probe",
    response_description="Service health status",
)
async def healthz() -> dict[str, str]:
    """
    Returns HTTP 200 + `{"status": "healthy"}` unconditionally.
    Use for both Kubernetes livenessProbe and readinessProbe.
    """
    return {"status": "healthy"}


@app.get(
    "/metrics",
    tags=["ops"],
    summary="Prometheus metrics scrape endpoint",
    response_description="Prometheus text-format metrics",
)
async def metrics() -> Response:
    """
    Exposes all registered Prometheus metrics in text exposition format.
    Scrape interval recommended: 15s–30s.
    """
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )


# ---------------------------------------------------------------------------
# Data Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/api/tickers",
    tags=["data"],
    summary="List all tracked assets with live data",
)
async def get_tickers() -> dict[str, Any]:
    """
    Returns the current in-memory state for every tracked cryptocurrency,
    including price, sentiment score, and last-updated timestamp.
    """
    return {
        asset_id: {
            "coingecko_id":     asset.coingecko_id,
            "keywords":         asset.keywords,
            "price_usd":        asset.price_usd,
            "sentiment_score":  asset.sentiment_score,
            "last_updated":     asset.last_updated,
        }
        for asset_id, asset in TRACKED_ASSETS.items()
    }


@app.get(
    "/api/tickers/{coin_id}",
    tags=["data"],
    summary="Get a single tracked asset by CoinGecko ID",
)
async def get_ticker(coin_id: str) -> dict[str, Any]:
    """Returns state for a single asset. 404 if not currently tracked."""
    coin_id = coin_id.lower().strip()
    if coin_id not in TRACKED_ASSETS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{coin_id}' is not currently tracked.",
        )
    asset = TRACKED_ASSETS[coin_id]
    return {
        "coingecko_id":     asset.coingecko_id,
        "keywords":         asset.keywords,
        "price_usd":        asset.price_usd,
        "sentiment_score":  asset.sentiment_score,
        "last_updated":     asset.last_updated,
    }


@app.post(
    "/api/ticker",
    status_code=status.HTTP_201_CREATED,
    tags=["data"],
    summary="Dynamically register a new cryptocurrency to track",
)
async def add_ticker(request: AddTickerRequest) -> dict[str, str]:
    """
    Adds a new `CryptoAsset` to the in-memory registry. The asset will be
    included in the very next ingestion loop cycle (within FETCH_INTERVAL_SECONDS).

    Example payload:
    ```json
    {"id": "cardano", "keywords": ["Cardano", "ADA"]}
    ```
    """
    coin_id = request.id  # already normalized by Pydantic validator

    if coin_id in TRACKED_ASSETS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Asset '{coin_id}' is already being tracked.",
        )

    TRACKED_ASSETS[coin_id] = CryptoAsset(
        coingecko_id=coin_id,
        keywords=request.keywords,
    )
    log.info(
        "New asset registered: %s keywords=%s",
        coin_id,
        request.keywords,
        extra={"ticker": coin_id},
    )
    return {"status": "added", "id": coin_id}


@app.delete(
    "/api/ticker/{coin_id}",
    tags=["data"],
    summary="Remove a tracked cryptocurrency by CoinGecko ID",
)
async def remove_ticker(coin_id: str) -> dict[str, str]:
    """
    Removes an asset from the tracking registry immediately.
    Its Prometheus gauge labels will persist until the process restarts
    (standard Prometheus label lifecycle behaviour).
    """
    coin_id = coin_id.lower().strip()
    if coin_id not in TRACKED_ASSETS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{coin_id}' is not currently tracked.",
        )
    del TRACKED_ASSETS[coin_id]
    log.info(
        "Asset deregistered: %s",
        coin_id,
        extra={"ticker": coin_id},
    )
    return {"status": "removed", "id": coin_id}


# ---------------------------------------------------------------------------
# Entrypoint — used when running directly (docker run / python app.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_config=None,   # Disable Uvicorn's default logger; JSON logger takes over
        access_log=False,  # Suppress default access log in favour of structured logs
    )
