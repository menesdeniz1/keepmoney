"""Servis katmanının paylaşılan yardımcıları.

Burada yalnızca BİRDEN ÇOK servisin aynı kuralı uygulaması gereken şeyler
bulunur. Tek bir servise ait mantık kendi dosyasında kalır.
"""
from __future__ import annotations

from typing import Any


def alanlari_uygula(nesne: Any, alanlar: dict, izinli: frozenset,
                    temizlenebilir: frozenset, hata: type[Exception]) -> None:
    """Kısmi güncellemeyi (PATCH) güvenli biçimde uygular.

    İKİ KURAL, tek yerde:

    1. BEYAZ LİSTE. Yalnızca `izinli` alanlar yazılır. Eskiden her iki servis
       de `hasattr(nesne, ad)` ile karar veriyordu — yani modelin HER sütunu
       yazılabilirdi. Şema bilinmeyen anahtarı düşürdüğü için sömürülebilir
       değildi, ama korumayı tesadüfe bırakmak toplu atama (mass assignment)
       açığının klasik reçetesidir: şemaya `user_id` eklendiği gün kullanıcı
       kaydı başkasına taşıyabilir.

    2. AÇIK `null` = TEMİZLE. Rotalar `exclude_unset=True` ile çağırıyor,
       yani bir anahtarın VARLIĞI kullanıcının o alana bilerek dokunduğu
       anlamına gelir. `None`u "dokunulmadı" saymak, bir kez konan hedef
       fiyatın/bütçenin API'den bir daha SİLİNEMEMESİ demekti.

    Kural iki serviste kopyalanmıştı ve biri düzeltilip diğeri geride
    kalmıştı; ortak yardımcı tam da bunu engellemek için var.
    """
    bilinmeyen = set(alanlar) - izinli
    if bilinmeyen:
        raise hata(f"Bu alanlar güncellenemez: {', '.join(sorted(bilinmeyen))}")

    for ad, deger in alanlar.items():
        if deger is None and ad not in temizlenebilir:
            continue          # boolean/zorunlu alanda null anlamsız
        setattr(nesne, ad, deger)
