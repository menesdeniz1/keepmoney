#!/usr/bin/env bash
#
# Yedekten geri yükleme.
#
# BU BETİK DÜZENLİ OLARAK DENENMELİDİR. Denenmemiş bir geri yükleme
# prosedürü, felaket anında ilk kez denenen prosedürdür — ve o an öğrenmek
# için en kötü andır. Ayda bir boş bir veritabanına geri yükleyip satır
# sayılarına bak.
#
#   ./betikler/geri-yukle.sh yedekler/keepmoney-20260815-033000.dump

set -euo pipefail

KAYNAK="${1:?Kullanım: geri-yukle.sh <yedek-dosyası>}"
: "${KEEPMONEY_VERITABANI_URL:?KEEPMONEY_VERITABANI_URL tanımlı olmalı}"

[[ -f "$KAYNAK" ]] || { echo "Dosya yok: $KAYNAK" >&2; exit 1; }

echo "!! Bu işlem hedef veritabanının İÇERİĞİNİ DEĞİŞTİRİR:"
echo "   $KEEPMONEY_VERITABANI_URL"
# ONAYSIZ=1 yalnızca otomatik tatbikat içindir (bkz. testler).
if [[ "${ONAYSIZ:-}" != "1" ]]; then
    read -r -p "Devam etmek için 'evet' yaz: " onay
    [[ "$onay" == "evet" ]] || { echo "İptal edildi."; exit 1; }
fi

if [[ "$KEEPMONEY_VERITABANI_URL" == sqlite* ]]; then
    HEDEF="${KEEPMONEY_VERITABANI_URL#sqlite:///}"
    GECICI="$(mktemp)"
    if [[ "$KAYNAK" == *.gz ]]; then
        gunzip -c "$KAYNAK" > "$GECICI"
    else
        cp "$KAYNAK" "$GECICI"
    fi

    # Bütünlük kontrolü geri yüklemeden ÖNCE yapılır: bozuk bir yedekle
    # çalışan veritabanının üzerine yazmak, tek felaketi ikiye çıkarır.
    python3 - "$GECICI" <<'PY' || { echo "Yedek bozuk — geri yükleme YAPILMADI." >&2; rm -f "$GECICI"; exit 1; }
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as b:
    sonuc = b.execute("PRAGMA integrity_check").fetchone()[0]
sys.exit(0 if sonuc == "ok" else 1)
PY

    mkdir -p "$(dirname "$HEDEF")"
    mv "$GECICI" "$HEDEF"
else
    PG_URL="$(python3 -c "import os,re; print(re.sub(r'^postgresql\+\w+://','postgresql://',os.environ['KEEPMONEY_VERITABANI_URL']))")"
    # --clean --if-exists: mevcut nesneleri düşürüp yeniden kurar.
    pg_restore --clean --if-exists --no-owner --no-privileges \
               --dbname="$PG_URL" "$KAYNAK"
fi

echo "Geri yüklendi. Şema sürümünü doğrula:  alembic current"
