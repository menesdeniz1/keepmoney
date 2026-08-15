"""Zaman dilimi politikası — TEK YER.

KARAR (bkz. docs/MIMARI.md K10): Ürün Türkiye pazarına yapılıyor.

  • VERİTABANINDA her zaman UTC saklanır (naive, SQLite uyumu için).
  • KULLANICIYA GÖSTERİLEN ve ANALİZDE KULLANILAN her şey Europe/Istanbul.

Neden bu ayrım kritik: "gün" sınırı günlük minimum hesabını doğrudan belirler.
UTC gününe göre gruplarsak, Türkiye saatiyle 01:00'de görülen bir fiyat düşüşü
BİR ÖNCEKİ günün minimumuna yazılır. Kullanıcı "dün 48.500'dü" derken Türkiye
gününü kastediyor; sistem başka bir gün kastediyorsa "son 30 günün dibi"
bildirimi yanlış günü işaret eder.

Kural: koda `datetime.now()` veya `date.today()` YAZMA. Buradaki fonksiyonları
kullan. (Linter DTZ kuralları bunu zorlar.)
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

TR = ZoneInfo("Europe/Istanbul")


def utc_simdi() -> datetime:
    """Veritabanına yazılacak zaman damgası: naive UTC.

    Naive tercih edildi çünkü SQLite saat dilimi bilgisini saklamaz ve
    yarı-aware bir şema en kötü seçenektir. Tüm DB değerleri UTC kabul edilir;
    tek dönüşüm noktası `tr_gun()` / `tr_saat()`.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def tr_simdi() -> datetime:
    """Şu anki Türkiye saati (aware)."""
    return datetime.now(TR)


def tr_bugun() -> date:
    """Türkiye takvimine göre bugün. Tüm 'gün' hesaplarının referansı."""
    return tr_simdi().date()


def tr_saat(dt: datetime) -> datetime:
    """Herhangi bir zaman damgasını Türkiye saatine çevirir.
    Naive girdi UTC kabul edilir (DB'den gelen her şey böyledir)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(TR)


def tr_gun(dt: datetime) -> date:
    """Bir zaman damgasının Türkiye takvimindeki günü.
    Günlük minimum gruplaması bunu kullanır."""
    return tr_saat(dt).date()


def sessiz_saat_mi(baslangic: int, bitis: int, dt: datetime | None = None) -> bool:
    """Türkiye saatine göre sessiz saat aralığında mıyız?
    Gece yarısını aşan aralıkları da doğru işler (örn. 23-8)."""
    saat = (tr_saat(dt) if dt else tr_simdi()).hour
    if baslangic <= bitis:
        return baslangic <= saat < bitis
    return saat >= baslangic or saat < bitis
