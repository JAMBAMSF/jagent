FROM python:3.11-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NLTK_DATA=/usr/local/share/nltk_data \
    GAGENT_DB_PATH=/data/gagent.sqlite \
    GAGENT_CACHE_CSV=/data/cache_prices.csv \
    MODE=cli

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tini ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python - <<'PY'\n\
import nltk, os\n\
os.makedirs(os.environ.get("NLTK_DATA","/usr/local/share/nltk_data"), exist_ok=True)\n\
try:\n\
    nltk.data.find("sentiment/vader_lexicon")\n\
except LookupError:\n\
    nltk.download("vader_lexicon")\n\
print("VADER ready.")\n\
PY

RUN useradd -m -u 10001 appuser && \
    mkdir -p /data "$NLTK_DATA" && \
    chown -R appuser:appuser /data "$NLTK_DATA"
USER appuser

COPY . .

EXPOSE 8501 8000

ENTRYPOINT ["/usr/bin/tini", "--"]

CMD ["/bin/sh", "-lc", "\
  if [ \"$MODE\" = \"streamlit\" ]; then \
    streamlit run streamlit_app.py; \
  elif [ \"$MODE\" = \"webhook\" ]; then \
    uvicorn server.webhook_finnhub:app --host 0.0.0.0 --port 8000; \
  else \
    python gagent.py --user \"${GAGENT_USER:-Graham Mercy}\"; \
  fi"]