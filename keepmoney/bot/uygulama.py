"""aiogram 3 bot uygulaması — İNCE katman.

Buradaki her handler tek iş yapar: isteği çözer, `servisler/`i çağırır,
`kartlar.py`den gelen metni yollar. İş kuralı YOK — aynı kurallar API'de de
çalışıyor ve iki yerde iki farklı davranış oluşmamalı (bkz. MIMARI K13).

Neden aiogram: python-telegram-bot'a göre async-yerli, router tabanlı yapısı
FastAPI'ninkine benziyor ve v3 ile tip desteği güçlü. Sürdürülen, güncel.
"""
from __future__ import annotations

import contextlib
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..ayarlar import ayarlar
from ..db import SessionLocal
from ..servisler import izleme as izleme_svc
from ..servisler import kullanici as kullanici_svc
from ..servisler import urun as urun_svc
from . import kartlar

log = logging.getLogger("keepmoney.bot")
dp = Dispatcher()


def _klavye(satirlar: list[list[dict]]) -> InlineKeyboardMarkup:
    """Saf sözlükleri aiogram nesnesine çevirir — dönüşüm TEK yerde."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=d["text"], callback_data=d["callback_data"])
         for d in satir]
        for satir in satirlar
    ])


async def _kullanici(chat_id: int | str):
    """Gelen mesajı hesaba çözer. None = bağlanmamış."""
    with SessionLocal() as db:
        return kullanici_svc.chat_id_ile(db, str(chat_id))


@dp.message(CommandStart(deep_link=True))
async def baslat_deep_link(mesaj: Message, command: CommandObject) -> None:
    """`/start <token>` — hesap bağlama.

    Kullanıcı chat ID kopyalamaz (bkz. MIMARI K7): siteden aldığı tek
    kullanımlık token'ı bot doğrular ve chat_id'yi sunucu tarafında yazar.
    """
    token = (command.args or "").strip()
    with SessionLocal() as db:
        k = kullanici_svc.telegram_dogrula(db, token, str(mesaj.chat.id))
        if k is None:
            await mesaj.answer(kartlar.baglama_basarisiz(), parse_mode="Markdown")
            return
        await mesaj.answer(kartlar.baglama_basarili(k.email), parse_mode="Markdown")


@dp.message(CommandStart())
async def baslat(mesaj: Message) -> None:
    k = await _kullanici(mesaj.chat.id)
    await mesaj.answer(
        kartlar.karsilama(k is not None, k.email if k else None),
        parse_mode="Markdown")


@dp.message(Command("yardim"))
async def yardim(mesaj: Message) -> None:
    await mesaj.answer(kartlar.YARDIM, parse_mode="Markdown")


@dp.message(Command("liste"))
async def liste(mesaj: Message) -> None:
    with SessionLocal() as db:
        k = kullanici_svc.chat_id_ile(db, str(mesaj.chat.id))
        if k is None:
            await mesaj.answer(kartlar.karsilama(False), parse_mode="Markdown")
            return
        izlemeler = izleme_svc.izlemeler(db, k)
        await mesaj.answer(kartlar.liste_metni(izlemeler), parse_mode="Markdown")


@dp.message(Command("durum"))
async def durum(mesaj: Message) -> None:
    with SessionLocal() as db:
        k = kullanici_svc.chat_id_ile(db, str(mesaj.chat.id))
        if k is None:
            await mesaj.answer(kartlar.karsilama(False), parse_mode="Markdown")
            return
        await mesaj.answer(
            kartlar.durum_metni(izleme_svc.izlemeler(db, k)),
            parse_mode="Markdown")


@dp.callback_query(F.data.startswith("hd:"))
async def hedef_menusu(cb: CallbackQuery) -> None:
    _, parcalar = kartlar.callback_coz(cb.data or "")
    izleme_id = int(parcalar[0])
    with SessionLocal() as db:
        k = kullanici_svc.chat_id_ile(db, str(cb.message.chat.id))
        if k is None:
            await cb.answer("Hesabın bağlı değil", show_alert=True)
            return
        try:
            w = izleme_svc.izleme_getir(db, k, izleme_id)
        except izleme_svc.IzlemeHatasi:
            await cb.answer("Bu ürün listende yok", show_alert=True)
            return
        fiyat = w.product.guncel_fiyat if w.product else None
        await cb.message.edit_reply_markup(
            reply_markup=_klavye(kartlar.hedef_secim_klavyesi(izleme_id, fiyat)))
    await cb.answer()


@dp.callback_query(F.data.startswith("hs:"))
async def hedef_secildi(cb: CallbackQuery) -> None:
    _, parcalar = kartlar.callback_coz(cb.data or "")
    izleme_id, yeni_hedef = int(parcalar[0]), float(parcalar[1])
    with SessionLocal() as db:
        k = kullanici_svc.chat_id_ile(db, str(cb.message.chat.id))
        if k is None:
            await cb.answer("Hesabın bağlı değil", show_alert=True)
            return
        try:
            izleme_svc.guncelle(db, k, izleme_id, hedef_fiyat=yeni_hedef)
        except izleme_svc.IzlemeHatasi:
            await cb.answer("Bu ürün listende yok", show_alert=True)
            return
    await cb.answer(f"Hedef güncellendi: {yeni_hedef:,.0f} ₺", show_alert=False)


@dp.callback_query(F.data.startswith("ss:"))
async def sustur(cb: CallbackQuery) -> None:
    _, parcalar = kartlar.callback_coz(cb.data or "")
    izleme_id, gun = int(parcalar[0]), int(parcalar[1])
    with SessionLocal() as db:
        k = kullanici_svc.chat_id_ile(db, str(cb.message.chat.id))
        if k is None:
            await cb.answer("Hesabın bağlı değil", show_alert=True)
            return
        try:
            izleme_svc.guncelle(db, k, izleme_id, sustur_gun=gun)
        except izleme_svc.IzlemeHatasi:
            await cb.answer("Bu ürün listende yok", show_alert=True)
            return
    await cb.answer(f"{gun} gün susturuldu")


@dp.callback_query(F.data.startswith("dr:"))
async def duraklat(cb: CallbackQuery) -> None:
    """Duraklat / Devam ettir.

    ÖLÜ DÜĞMEYDİ: klavye `dr:` üretiyordu ama karşılığında hiçbir handler
    yoktu — kullanıcı basıyor, Telegram dönen çarkı gösterip susuyordu.
    "JSX'te düğme var" ile "düğme çalışıyor" arasındaki farkın bot tarafındaki
    hâli; klavye kodları ile handler'lar arasındaki boşluğu artık bir test
    koruyor.
    """
    _, parcalar = kartlar.callback_coz(cb.data or "")
    izleme_id = int(parcalar[0])
    with SessionLocal() as db:
        k = kullanici_svc.chat_id_ile(db, str(cb.message.chat.id))
        if k is None:
            await cb.answer("Hesabın bağlı değil", show_alert=True)
            return
        try:
            w = izleme_svc.izleme_getir(db, k, izleme_id)
            yeni = not bool(w.aktif)
            izleme_svc.guncelle(db, k, izleme_id, aktif=yeni)
            w = izleme_svc.izleme_getir(db, k, izleme_id)
        except izleme_svc.IzlemeHatasi:
            await cb.answer("Bu ürün listende yok", show_alert=True)
            return
        # Düğme metni durumu göstermeli: basınca "Duraklat" → "Devam ettir".
        with contextlib.suppress(Exception):
            await cb.message.edit_reply_markup(
                reply_markup=_klavye(kartlar.urun_klavyesi(izleme_id, yeni)))
    await cb.answer("Takip sürüyor" if yeni else "Duraklatıldı")


@dp.callback_query(F.data.startswith("he:"))
async def hedef_elle(cb: CallbackQuery) -> None:
    """"✍️ Elle yaz" — hedefi kullanıcı yazsın.

    ÖLÜ DÜĞMEYDİ (bkz. yukarısı). Yüzdelik kısayollar çoğu durumu çözüyor
    ama "şu fiyatın altına insin" demek isteyen kullanıcının başka yolu yoktu.

    DURUM TUTULMUYOR: aiogram FSM yerine Telegram'ın `ForceReply`si
    kullanılıyor. Hangi ürün olduğu, kullanıcının YANITLADIĞI mesajın içinde
    duruyor (`#<id>`) — yani bot yeniden başlasa da akış bozulmuyor. Süreç
    belleğinde durum tutmak, worker/bot yeniden başladığında kullanıcıyı
    yarım kalmış bir diyalogda bırakırdı.
    """
    _, parcalar = kartlar.callback_coz(cb.data or "")
    izleme_id = int(parcalar[0])
    await cb.message.answer(
        kartlar.hedef_iste_metni(izleme_id),
        parse_mode="Markdown",
        reply_markup=ForceReply(input_field_placeholder="örn. 45000"))
    await cb.answer()


@dp.message(F.reply_to_message)
async def hedef_yaniti(mesaj: Message) -> None:
    """Kullanıcı `ForceReply` mesajına cevap verdi: hedefi yaz."""
    kaynak = (mesaj.reply_to_message.text or "") if mesaj.reply_to_message else ""
    izleme_id = kartlar.hedef_isteginden_id(kaynak)
    if izleme_id is None:
        # Başka bir mesaja verilmiş yanıt — arama gibi davran.
        await serbest_metin(mesaj)
        return

    hedef = kartlar.sayi_coz(mesaj.text or "")
    if hedef is None:
        await mesaj.answer("Anlamadım. Sadece sayı yaz: `45000`",
                           parse_mode="Markdown")
        return

    with SessionLocal() as db:
        k = kullanici_svc.chat_id_ile(db, str(mesaj.chat.id))
        if k is None:
            await mesaj.answer(kartlar.karsilama(False), parse_mode="Markdown")
            return
        try:
            izleme_svc.guncelle(db, k, izleme_id, hedef_fiyat=hedef)
            w = izleme_svc.izleme_getir(db, k, izleme_id)
        except izleme_svc.IzlemeHatasi:
            await mesaj.answer("Bu ürün listende yok.")
            return
        await mesaj.answer(kartlar.hedef_kondu_metni(w, hedef),
                           parse_mode="Markdown",
                           reply_markup=_klavye(
                               kartlar.urun_klavyesi(w.id, w.aktif)))


@dp.callback_query(F.data.startswith("sl:"))
async def sil(cb: CallbackQuery) -> None:
    _, parcalar = kartlar.callback_coz(cb.data or "")
    with SessionLocal() as db:
        k = kullanici_svc.chat_id_ile(db, str(cb.message.chat.id))
        if k is None:
            await cb.answer("Hesabın bağlı değil", show_alert=True)
            return
        try:
            izleme_svc.sil(db, k, int(parcalar[0]))
        except izleme_svc.IzlemeHatasi:
            await cb.answer("Bu ürün listende yok", show_alert=True)
            return
    await cb.answer("Takipten çıkarıldı")


# Filtre ile ayıklayıcı AYNI deseni kullanır (`kartlar.LINK`).
#
# Burada `F.text.regexp(...)` VARDI ve ölçüldü: aiogram onu `re.match` ile
# uyguluyor, yani deseni metnin BAŞINA sabitliyor. "şuna bak https://… fiyatı
# düştü" gibi cümle içine gömülü linkler — Telegram'da en yaygın biçim —
# handler'a hiç ulaşmıyor, arama handler'ına düşüp "ürün bulamadım" cevabı
# alıyordu. `func` ile `search` kullanılıyor.
@dp.message(F.text.func(lambda t: bool(kartlar.LINK.search(t or ""))))
async def link_ekle(mesaj: Message) -> None:
    """Bota LİNK yapıştırınca ürünü takibe alır.

    NEDEN VAR: bot komutları ürünü listeliyor, hedefini değiştiriyor,
    susturuyor ve siliyordu — ama EKLEYEMİYORDU; yardım metni "siteye link
    yapıştır" diyordu. Yani telefondayken (asıl kullanım biçimi bu) yeni bir
    ürün eklemek için bilgisayara gitmek gerekiyordu. Öncül projede (`tracker`)
    bu vardı ve porta taşınmamıştı.

    İŞ KURALI BURADA YOK: aynı `izleme_svc.ekle` çağrılıyor — yani kota,
    kanonik URL birleştirme, SSRF koruması ve "zaten izliyorsun" kontrolü
    web ile BİREBİR aynı (K13). İkinci bir ekleme yolu yazmak, iki farklı
    davranış demek olurdu.

    Hedef fiyat isteğe bağlı: linkten sonra bir sayı yazılırsa hedef olur
    ("<link> 45000"). Yazılmazsa ürün hedefsiz eklenir, hedef sonra
    karttaki düğmelerden konur.
    """
    with SessionLocal() as db:
        k = kullanici_svc.chat_id_ile(db, str(mesaj.chat.id))
        if k is None:
            await mesaj.answer(kartlar.karsilama(False), parse_mode="Markdown")
            return

        url, hedef = kartlar.link_ve_hedef(mesaj.text or "")
        try:
            w = izleme_svc.ekle(db, k, url, hedef_fiyat=hedef)
        except izleme_svc.KotaDoldu as e:
            await mesaj.answer(f"⚠️ {e}")
            return
        except izleme_svc.IzlemeHatasi as e:
            # "Zaten izliyorsun" ve "iç ağ adresi izlenemez" gibi ANLAMLI
            # sebepler; kullanıcıya olduğu gibi söylenir.
            await mesaj.answer(f"⚠️ {e}")
            return

        await mesaj.answer(kartlar.eklendi_metni(w, hedef), parse_mode="Markdown",
                           reply_markup=_klavye(
                               kartlar.urun_klavyesi(w.id, w.aktif)))


@dp.message(F.text)
async def serbest_metin(mesaj: Message) -> None:
    """Komut olmayan mesaj: ürün adıyla arama."""
    with SessionLocal() as db:
        k = kullanici_svc.chat_id_ile(db, str(mesaj.chat.id))
        if k is None:
            await mesaj.answer(kartlar.karsilama(False), parse_mode="Markdown")
            return

        sorgu = (mesaj.text or "").casefold().strip()
        bulunan = [
            w for w in izleme_svc.izlemeler(db, k)
            if w.product and sorgu in w.product.ad.casefold()
        ]
        if not bulunan:
            await mesaj.answer(
                "Bu isimde bir ürün bulamadım. /liste ile hepsini görebilirsin.")
            return

        w = bulunan[0]
        baglam = urun_svc.baglam(db, w.product)
        metin = kartlar.urun_karti(
            w, None, baglam["yorum"] if baglam else "Henüz yeterli geçmiş yok.")
        await mesaj.answer(
            metin, parse_mode="Markdown",
            reply_markup=_klavye(kartlar.urun_klavyesi(w.id, w.aktif)))


class AiogramPostaci:
    """`gonderici.Postaci` uygulaması — gerçek Telegram gönderimi."""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def gonder(self, chat_id: str, metin: str) -> bool:
        try:
            await self.bot.send_message(chat_id, metin, parse_mode="Markdown")
            return True
        except Exception as e:
            log.warning("Telegram gönderimi başarısız (chat=%s): %s", chat_id, e)
            return False


def bot_olustur() -> Bot | None:
    """Token yoksa None — bot isteğe bağlı bir bileşendir, yokluğu sistemi
    durdurmaz (web tek başına tamamen çalışır)."""
    token = ayarlar().telegram_bot_token
    if not token:
        log.info("TELEGRAM_BOT_TOKEN yok — bot devre dışı")
        return None
    return Bot(token=token)


async def calistir() -> None:
    """Uzun yoklama ile bot döngüsü. `python -m keepmoney.bot` ile çalışır."""
    bot = bot_olustur()
    if bot is None:
        return
    log.info("Telegram botu başlatılıyor (uzun yoklama)")
    await dp.start_polling(bot)
