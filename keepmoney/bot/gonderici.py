"""Uyarı gönderici — DB'deki uyarıları Telegram'a iletir.

ÜRETİM ile İLETİM bilerek ayrı (outbox kalıbı):
  worker → Alert satırı yazar (telegram_gonderildi=False)
  gönderici → iletir, bayrağı çevirir

Neden ayrı: Telegram kesintisi tarama turunu durdurmamalı; uyarı da
kaybolmamalı. Worker'ın içinden HTTP çağırmak ikisini de riske atardı — tarama
yavaşlar, hata anında uyarı buharlaşır. Outbox kalıbı bunun standart cevabıdır.

Gönderim başarısızsa bayrak çevrilmez → sonraki turda yeniden denenir.
"""
from __future__ import annotations

import logging
from typing import Protocol

from sqlalchemy.orm import Session

from ..models import Alert, User
from .kartlar import uyari_mesaji

log = logging.getLogger("keepmoney.bot.gonderici")

# Tek turda gönderilecek azami uyarı. Telegram bot API'si sohbet başına
# ~1 mesaj/sn kabul eder; toplu birikmede kullanıcıyı da bombalamayalım.
TUR_BASINA_LIMIT = 30

# Bir uyarı kaç kez denendikten sonra bırakılır.
#
# SINIRSIZ DENEME KUYRUĞUN BAŞINI TIKIYORDU: sorgu `created_at`e göre sıralı
# ve `limit`li. Bir kullanıcı botu bloklarsa Telegram KALICI hata döner, o
# uyarılar hiç temizlenmez ve zamanla kuyruğun başını tamamen doldurur —
# ÖLÇÜLDÜ: 30 tıkalı uyarı + 1 yeni uyarıyla 5 tur koşuldu, yeni uyarı BİR
# KEZ BİLE denenmedi. Yani tek bir kullanıcının botu bloklaması, ürünün
# ana değer teslimini HERKES için durduruyordu.
#
# 5 seçildi: geçici bir Telegram kesintisi (dakikada bir tur → ~5 dakika)
# atlatılabilsin ama kalıcı hata sonsuza kadar denenmesin.
TELEGRAM_AZAMI_DENEME = 5


class Postaci(Protocol):
    """Gönderim arayüzü. Testler sahte bir uygulama verir — gerçek ağa
    çıkmadan tüm akış doğrulanabilsin."""

    async def gonder(self, chat_id: str, metin: str) -> bool: ...


async def bekleyenleri_gonder(db: Session, postaci: Postaci,
                              limit: int = TUR_BASINA_LIMIT) -> int:
    """İletilmemiş uyarıları gönderir, gönderilen sayısını döner."""
    bekleyen = (
        db.query(Alert)
        .filter(Alert.telegram_gonderildi.is_(False),
                Alert.telegram_deneme < TELEGRAM_AZAMI_DENEME)
        .order_by(Alert.created_at)
        .limit(limit)
        .all()
    )
    if not bekleyen:
        return 0

    # chat_id'leri tek sorguda çöz (uyarı başına sorgu atmayalım)
    kullanici_ids = {a.user_id for a in bekleyen}
    chatler = {
        k.id: k.telegram_chat_id
        for k in db.query(User).filter(User.id.in_(kullanici_ids)).all()
    }

    gonderilen = 0
    for uyari in bekleyen:
        chat_id = chatler.get(uyari.user_id)
        if not chat_id:
            # Kullanıcı Telegram'ı bağlamamış — uyarı web'de duruyor, iletim
            # gerekmiyor. Bayrağı çevir ki her turda yeniden denenmesin.
            uyari.telegram_gonderildi = True
            continue

        try:
            basarili = await postaci.gonder(chat_id, uyari_mesaji(uyari))
        except Exception as e:                    # ağ hatası turu düşürmesin
            log.warning("Uyarı %s iletilemedi: %s", uyari.id, e)
            basarili = False

        if basarili:
            uyari.telegram_gonderildi = True
            gonderilen += 1
            continue

        # BAŞARISIZ. Bayrak ÇEVRİLMEZ (gönderilmedi), ama deneme sayılır:
        # eşiği aşan uyarı bir daha çekilmez ve kuyruğun başını tıkamaz.
        uyari.telegram_deneme = (uyari.telegram_deneme or 0) + 1
        if uyari.telegram_deneme >= TELEGRAM_AZAMI_DENEME:
            log.warning(
                "Uyarı %s %s denemeden sonra bırakıldı (chat=%s) — "
                "kullanıcı botu engellemiş olabilir; uyarı web'de duruyor",
                uyari.id, uyari.telegram_deneme, chat_id)

    db.commit()
    if gonderilen:
        log.info("%s uyarı Telegram'a iletildi", gonderilen)
    return gonderilen
