#!/bin/bash
# ===================================================================
#  KeepMoney - CIFT TIKLA KURULUM  (macOS)
# ===================================================================
#
#  `kur.bat`in macOS karsiligi. Mantik yine betikler/kurulum.py icinde;
#  burada yalnizca "dogru klasore gec + calisir bir Python bul" var.
#
#  .command uzantisi: macOS'ta cift tiklaninca Terminal'de calisir.
#  Ilk seferde "izin verilmedi" derse:  chmod +x kur.command
#
#  ILK SATIRDAN SONRA `cd` SART: Finder'dan cift tiklanan betik ev
#  dizininde baslar, betigin bulundugu klasorde degil.
# ===================================================================
set -u
cd "$(dirname "$0")" || exit 1

echo "KeepMoney kurulumu — $(pwd)"
echo

# Python 3.12+ ara. macOS'un kendi python3'u eski olabilir; Homebrew
# surumu once denenir.
PY=""
for aday in /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 \
            /usr/local/bin/python3.13 /usr/local/bin/python3.12 \
            python3.13 python3.12 python3; do
  if command -v "$aday" >/dev/null 2>&1; then
    surum=$("$aday" -c 'import sys; print(sys.version_info[0]*100+sys.version_info[1])' 2>/dev/null || echo 0)
    if [ "$surum" -ge 312 ] 2>/dev/null; then PY="$aday"; break; fi
  fi
done

if [ -z "$PY" ]; then
  cat <<'YOK'

  Python 3.12 veya yenisi bulunamadi.

  En kolay yol (Homebrew):
    1) Terminal'i ac ve sunu yapistir:
       /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    2) Bitince:
       brew install python@3.12
    3) Bu dosyaya tekrar cift tikla.

  Homebrew istemiyorsan: https://www.python.org/downloads/macos/

YOK
  echo "Kapatmak icin bu pencereyi kapatabilirsin."
  read -r -p "Enter'a bas..." _
  exit 1
fi

echo "Python: $PY ($("$PY" --version 2>&1))"
"$PY" betikler/kurulum.py kur
KOD=$?

echo
if [ $KOD -eq 0 ]; then
  echo "Simdi basla.command dosyasina cift tikla."
fi
read -r -p "Enter'a basinca pencere kapanir..." _
exit $KOD
