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

# pip/setuptools önce güncellenir: taban imajdaki sürümlerde bilinen
# açıklar çıkabiliyor (pip-audit yakaladı) ve bunlar uygulamanın kendi
# bağımlılıkları değil, imajın taşıdığı araçlar.
RUN pip install --no-cache-dir --upgrade pip setuptools

COPY requirements.txt .
RUN pip install -r requirements.txt

# Tarayıcı motoru. İMAJI ~400 MB BÜYÜTÜR ve buna rağmen zorunludur: akakçe,
# cimri, trendyol ve amazon kuralları `render: true` istiyor. Playwright
# olmadan çekim zinciri sessizce `requests`e düşüyor ve o kaynaklardan HİÇ
# fiyat gelmiyordu — hiçbir log da bunu söylemiyordu. Üstelik toplayıcılar
# maliyet modelinin merkezinde: 10 mağaza taramak yerine 1 sayfa okumak.
#
# `--with-deps` sistem kütüphanelerini de kurar; onlarsız chromium slim
# imajda açılmaz.
#
# PLAYWRIGHT_BROWSERS_PATH ŞART. Kurulum root olarak yapılıyor ve varsayılan
# hedef `~/.cache/ms-playwright`, yani `/root/.cache/...`. Konteyner ise
# `kmuser` olarak koşuyor ve `/root` dizinine erişemez: tarayıcı imajın
# içinde DURUR ama çalışma zamanında BULUNAMAZ. Hata da net değildir —
# çekim zinciri sessizce `requests`e düşer ve `render: true` siteler hiç
# okunmaz. Herkesin okuyabildiği bir dizine kuruluyor.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
RUN pip install --no-cache-dir playwright \
    && playwright install --with-deps chromium \
    && chmod -R a+rX /opt/pw-browsers

COPY keepmoney/ ./keepmoney/
COPY migrations/ ./migrations/
COPY alembic.ini .
# Derlenmiş arayüz. API bunu AYNI KAYNAKTAN sunar (bkz. api/statik.py) —
# bir dönem buraya kopyalanıyor ama hiç sunulmuyordu, yani üretimde web
# panosu tamamen erişilemezdi.
COPY --from=arayuz /arayuz/dist ./statik

# Kök olmayan kullanıcı: konteyner ele geçirilse bile host'a sıçrama zorlaşır.
RUN useradd --create-home --uid 10001 kmuser && chown -R kmuser /uygulama
USER kmuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/saglik || exit 1

CMD ["uvicorn", "keepmoney.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
