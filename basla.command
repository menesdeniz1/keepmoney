#!/bin/bash
# ===================================================================
#  KeepMoney - CIFT TIKLA CALISTIR  (macOS)
# ===================================================================
#
#  Ortami dogrular, API + tarama worker'ini baslatir, tarayiciyi acar.
#  Surekli calismasi icin bunu elle acmak yerine launchd kullan:
#    betikler/macos/kur-servis.sh    (acilista otomatik kalkar)
#
#  TELEFONDAN ERISIM: `.env` icine `KEEPMONEY_DINLEME=0.0.0.0` yaz.
#  O zaman ayni Wi-Fi'daki cihazlar Mac'in IP'sinden erisebilir.
#  Adresi bu betik calisirken ekrana basiyor.
# ===================================================================
set -u
cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/python" ]; then
  echo
  echo "  Sanal ortam yok: .venv/bin/python bulunamadi."
  echo "  Once kur.command dosyasina cift tikla."
  echo
  read -r -p "Enter'a bas..." _
  exit 1
fi

.venv/bin/python betikler/kurulum.py basla
KOD=$?

if [ $KOD -eq 0 ]; then
  # Ev agindaki adresi goster: telefondan bu adrese girilecek.
  IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "")
  if [ -n "$IP" ]; then
    echo
    echo "  Telefondan (ayni Wi-Fi):  http://$IP:8000"
    echo "  (Calismazsa .env icinde KEEPMONEY_DINLEME=0.0.0.0 olmali)"
  fi
else
  read -r -p "Enter'a bas..." _
fi
exit $KOD
