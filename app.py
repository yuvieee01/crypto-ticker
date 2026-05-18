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