#!/bin/bash
# ===================================================================
#  KeepMoney - CIFT TIKLA DURDUR  (macOS)
# ===================================================================
#  basla.command ile acilan API ve tarama worker'ini kapatir.
#  launchd servisi kuruluysa onu durdurmaz — servis icin:
#    betikler/macos/kur-servis.sh --kaldir
# ===================================================================
set -u
cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/python" ]; then
  echo "  Sanal ortam yok; kapatilacak bir sey de yok gibi gorunuyor."
  read -r -p "Enter'a bas..." _
  exit 1
fi

.venv/bin/python betikler/kurulum.py dur
echo
read -r -p "Enter'a basinca pencere kapanir..." _
