#!/usr/bin/env bash
#
# Veritabanı yedeği.
#
# NEDEN ÖNEMLİ: bu üründe asıl değer fiyat GEÇMİŞİDİR ve geçmiş yeniden
# üretilemez. Kod kaybolursa yeniden yazılır, sunucu kaybolursa yenisi
# kurulur; ama iki yıllık fiyat hafızası kaybolursa geri getirmenin yolu
# yoktur — ürünün tek gerçek varlığı odur.
#
# KULLANIM
#   ./betikler/yedekle.sh                        # varsayılan ./yedekler
#   YEDEK_DIZIN=/mnt/yedek ./betikler/yedekle.sh
#
# ZAMANLAMA (crontab, her gece 03:30):
#   30 3 * * * cd /opt/keepmoney && ./betikler/yedekle.sh >> /var/log/km-yedek.log 2>&1
#
# GERİ YÜKLEME: ./betikler/geri-yukle.sh <dosya>
#
# UYARI: Yedeği AYNI sunucuda tutmak yedek değildir — disk arızası ikisini
# birden götürür. YEDEK_DIZIN başka bir makineye ya da nesne deposuna bağlı
# olmalı.

set -euo pipefail

YEDEK_DIZIN="${YEDEK_DIZIN:-./yedekler}"
SAKLAMA_GUN="${SAKLAMA_GUN:-14}"
DAMGA="$(date +%Y%m%d-%H%M%S)"

: "${KEEPMONEY_VERITABANI_URL:?KEEPMONEY_VERITABANI_URL tanımlı olmalı}"

mkdir -p "$YEDEK_DIZIN"

if [[ "$KEEPMONEY_VERITABANI_URL" == sqlite* ]]; then
    # SQLite online yedek API. `cp` ile FARKI: yazma sürerken tutarlı bir
    # anlık görüntü alır; kopyalama yarım işlem yakalayabilir.
    #
    # `sqlite3` komut satırı aracı yerine Python modülü kullanılıyor: aynı
    # API, ek bağımlılık yok. Uygulama zaten Python; CLI aracının her
    # kurulumda bulunduğunu varsaymak betiği kırılgan yapardı.
    DOSYA="${KEEPMONEY_VERITABANI_URL#sqlite:///}"
    HEDEF="$YEDEK_DIZIN/keepmoney-$DAMGA.sqlite"
    python3 - "$DOSYA" "$HEDEF" <<'PY'
import sqlite3
import sys

kaynak, hedef = sys.argv[1], sys.argv[2]
with sqlite3.connect(kaynak) as k, sqlite3.connect(hedef) as h:
    k.backup(h)
PY
    gzip -f "$HEDEF"
    HEDEF="$HEDEF.gz"
else
    # Postgres: --format=custom → seçmeli ve paralel geri yükleme mümkün.
    PG_URL="$(python3 -c "import os,re; print(re.sub(r'^postgresql\+\w+://','postgresql://',os.environ['KEEPMONEY_VERITABANI_URL']))")"
    HEDEF="$YEDEK_DIZIN/keepmoney-$DAMGA.dump"
    pg_dump --format=custom --no-owner --no-privileges \
            --dbname="$PG_URL" --file="$HEDEF"
fi

echo "Yedek alındı: $HEDEF ($(du -h "$HEDEF" | cut -f1))"

# YEDEK DOĞRULANIR. Doğrulanmamış yedek, yedek değil temennidir: bozuk
# olduğu ancak felaket anında anlaşılır.
if [[ "$HEDEF" == *.gz ]]; then
    gzip -t "$HEDEF" && echo "Doğrulama: arşiv sağlam"
else
    pg_restore --list "$HEDEF" > /dev/null \
        && echo "Doğrulama: döküm içindekileri okunabiliyor"
fi

# Eski yedekleri temizle — disk dolarsa yedekleme sessizce durur.
find "$YEDEK_DIZIN" -name 'keepmoney-*' -type f -mtime "+$SAKLAMA_GUN" -delete
echo "Saklama: $SAKLAMA_GUN günden eski yedekler silindi"
