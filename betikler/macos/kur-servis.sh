#!/bin/bash
# ===================================================================
#  KeepMoney'i macOS'ta 7/24 calisan bir servis yapar (launchd)
# ===================================================================
#
#  NEDEN launchd, Docker degil:
#    • 8 GB M1'de Docker Desktop tek basina ~2 GB yiyor; ustune chromium
#      (istek basina ~250 MB) eklenince makine surunur.
#    • launchd, macOS'un kendi servis yoneticisi: acilista baslatir,
#      surec olurse YENIDEN BASLATIR, log dosyasi tutar.
#    • Tek kullanicilik kurulumda Postgres'e gerek yok; SQLite yeterli
#      ve yedegi TEK DOSYA (bkz. docs/CALISTIRMA.md).
#
#  UC AYRI SERVIS, cunku ariza modlari farkli (bkz. compose.yaml):
#    api      → web arayuzu
#    tarayici → fiyat okuma dongusu (asil is)
#    bot      → Telegram (token varsa)
#
#  KULLANIM
#    ./betikler/macos/kur-servis.sh            kur ve baslat
#    ./betikler/macos/kur-servis.sh --kaldir   durdur ve kaldir
#    ./betikler/macos/kur-servis.sh --durum    calisiyor mu
# ===================================================================
set -euo pipefail

KOK="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$KOK/.venv/bin/python"
LOG="$KOK/data/loglar"
PLIST_DIZIN="$HOME/Library/LaunchAgents"
ONEK="com.keepmoney"

servisler=(api tarayici bot)
# `yedek` de kaldirilmali ama servis degil, zamanlanmis is.
kaldirilacaklar=(api tarayici bot yedek)

komut_api="$PY -m uvicorn keepmoney.api.app:app --host \${HOST} --port 8000"
komut_tarayici="$PY -m keepmoney.zamanlayici"
komut_bot="$PY -m keepmoney.bot"

kullanim() { sed -n '2,30p' "$0"; exit 1; }

durum() {
  for s in "${kaldirilacaklar[@]}"; do
    if launchctl list | grep -q "$ONEK.$s"; then
      satir=$(launchctl list | grep "$ONEK.$s")
      pid=$(echo "$satir" | awk '{print $1}')
      cikis=$(echo "$satir" | awk '{print $2}')
      if [ "$pid" != "-" ]; then
        echo "  $s: CALISIYOR (pid $pid)"
      else
        echo "  $s: DURMUS (son cikis kodu $cikis) — log: $LOG/$s.log"
      fi
    else
      echo "  $s: kurulu degil"
    fi
  done
}

kaldir() {
  for s in "${kaldirilacaklar[@]}"; do
    launchctl bootout "gui/$(id -u)/$ONEK.$s" 2>/dev/null || true
    rm -f "$PLIST_DIZIN/$ONEK.$s.plist"
  done
  echo "Servisler kaldirildi. (Veritabani ve loglar DURUYOR.)"
}

case "${1:-}" in
  --kaldir) kaldir; exit 0 ;;
  --durum)  durum;  exit 0 ;;
  --help|-h) kullanim ;;
  "") : ;;
  *) kullanim ;;
esac

# ── Onkosullar ────────────────────────────────────────────────────
[ -x "$PY" ] || { echo "HATA: $PY yok. Once kur.command calistir."; exit 1; }
"$PY" "$KOK/betikler/kurulum.py" dogrula || {
  echo
  echo "Ortam eksik; servis kurulmadi. Yukaridaki cozumleri uygula."
  exit 1
}

mkdir -p "$LOG" "$PLIST_DIZIN"

# `.env` icinde KEEPMONEY_DINLEME varsa onu kullan (telefondan erisim).
HOST=$(grep -E '^KEEPMONEY_DINLEME=' "$KOK/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d ' ' || true)
HOST=${HOST:-127.0.0.1}
echo "API dinleme adresi: $HOST"

# Telegram token'i yoksa bot servisi kurulmaz — token olmadan surekli
# yeniden baslayip log doldururdu.
TOKEN=$(grep -E '^KEEPMONEY_TELEGRAM_BOT_TOKEN=' "$KOK/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d ' ' || true)
if [ -z "$TOKEN" ]; then
  echo "Telegram token'i yok → bot servisi ATLANIYOR (.env'e yazip tekrar calistir)."
  servisler=(api tarayici)
fi

plist_yaz() {
  local ad="$1" komut="$2"
  cat > "$PLIST_DIZIN/$ONEK.$ad.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$ONEK.$ad</string>

  <!-- Komut, kabuk YOLUYLA degil dogrudan calistirilir. -->
  <key>ProgramArguments</key>
  <array>
$(for parca in $komut; do echo "    <string>$parca</string>"; done)
  </array>

  <!-- Calisma dizini SART: goreli yollar (data/, statik/) buna bagli. -->
  <key>WorkingDirectory</key><string>$KOK</string>

  <key>RunAtLoad</key><true/>
  <!-- Surec olurse yeniden baslat. Asil sebep bu: elektrik kesintisi,
       cokme ya da ag hatasi sonrasi sistem kendi kendine toparlasin. -->
  <key>KeepAlive</key><true/>
  <!-- Cokme dongusune girerse saniyede bir yeniden baslatmasin. -->
  <key>ThrottleInterval</key><integer>30</integer>

  <key>StandardOutPath</key><string>$LOG/$ad.log</string>
  <key>StandardErrorPath</key><string>$LOG/$ad.log</string>
</dict>
</plist>
PLIST
}

for s in "${servisler[@]}"; do
  degisken="komut_$s"
  komut="${!degisken}"
  komut="${komut//\$\{HOST\}/$HOST}"
  plist_yaz "$s" "$komut"
  launchctl bootout "gui/$(id -u)/$ONEK.$s" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST_DIZIN/$ONEK.$s.plist"
  echo "  $s kuruldu"
done

# ── Gunluk yedek (03:30) ──────────────────────────────────────────
#
# Bu urunde asil deger FIYAT GECMISIDIR ve yeniden uretilemez: kod
# kaybolursa yazilir, Mac kaybolursa yenisi alinir, iki yillik fiyat
# hafizasi kaybolursa geri getirmenin yolu YOKTUR.
#
# `.env` kabuga SOURCE EDILMIYOR: icinde `KeepMoney <noreply@...>` gibi
# degerler var ve `<` kabukta yonlendirmedir — dosyayi source etmek
# betigi kirardi. Deger grep ile cekiliyor.
DB_URL=$(grep -E '^KEEPMONEY_VERITABANI_URL=' "$KOK/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d ' ' || true)
DB_URL=${DB_URL:-sqlite:///./data/keepmoney.sqlite}
YEDEK_DIZIN=$(grep -E '^KEEPMONEY_YEDEK_DIZIN=' "$KOK/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d ' ' || true)
YEDEK_DIZIN=${YEDEK_DIZIN:-$KOK/yedekler}

cat > "$PLIST_DIZIN/$ONEK.yedek.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$ONEK.yedek</string>
  <key>ProgramArguments</key>
  <array>
    <string>$KOK/betikler/yedekle.sh</string>
  </array>
  <key>WorkingDirectory</key><string>$KOK</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>KEEPMONEY_VERITABANI_URL</key><string>$DB_URL</string>
    <key>YEDEK_DIZIN</key><string>$YEDEK_DIZIN</string>
  </dict>
  <!-- Her gece 03:30. KeepAlive YOK: bu tek seferlik bir is, servis degil. -->
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>$LOG/yedek.log</string>
  <key>StandardErrorPath</key><string>$LOG/yedek.log</string>
</dict>
</plist>
PLIST
launchctl bootout "gui/$(id -u)/$ONEK.yedek" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DIZIN/$ONEK.yedek.plist"
echo "  yedek kuruldu (her gece 03:30 → $YEDEK_DIZIN)"

echo
echo "Durum:"
sleep 2
durum

cat <<SON

Loglar: $LOG/
Durdurmak icin:  $0 --kaldir

SIRADAKI ADIM — MAC UYUMASIN:
  Sistem Ayarlari > Kilit Ekrani > "Ekran kapaliyken uyut" = Asla
  ve/veya:  sudo pmset -a sleep 0 disksleep 0
  Mac uyursa tarama DURUR; kapak kapaliyken calismasi icin guc kablosu
  takili olmali.
SON
