# ── Arayüz derlemesi ─────────────────────────────────────────────
FROM node:22-alpine AS arayuz
WORKDIR /arayuz
# Önce bağımlılıklar: kaynak değişince npm ci katmanı önbellekten gelsin.
COPY arayuz/package*.json ./
RUN npm ci
COPY arayuz/ ./
RUN npm run build

# ── Python katmanı ───────────────────────────────────────────────
FROM python:3.12-slim AS taban
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /uygulama

# lxml derlemesi için gerekli; sonra silinmiyor çünkü slim imajda
# çalışma zamanı kütüphaneleri de lazım.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 libxslt1.1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY keepmoney/ ./keepmoney/
COPY migrations/ ./migrations/
COPY alembic.ini .
COPY --from=arayuz /arayuz/dist ./statik

# Kök olmayan kullanıcı: konteyner ele geçirilse bile host'a sıçrama zorlaşır.
RUN useradd --create-home --uid 10001 kmuser && chown -R kmuser /uygulama
USER kmuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/saglik || exit 1

CMD ["uvicorn", "keepmoney.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
