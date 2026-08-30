"""Uyarı (bildirim) use-case'leri."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Alert, User

VARSAYILAN_LIMIT = 50
AZAMI_LIMIT = 100


def listele(db: Session, kullanici: User, sadece_okunmamis: bool = False,
            limit: int = VARSAYILAN_LIMIT, offset: int = 0,
            tur: list[str] | None = None, watch_id: int | None = None) -> list[Alert]:
    """Bildirimler, en yeniden eskiye, SAYFALI.

    Sayfalama yalnızca hız için değil ERİŞİLEBİLİRLİK için: liste sabit 50'de
    kesiliyordu ve daha eski bildirimlere ulaşmanın hiçbir yolu yoktu.
    Üst sınır (`AZAMI_LIMIT`) korunur — istemcinin `limit=100000` diyerek
    tabloyu belleğe çekmesi engellenmeli.

    Sıralamada `id` ikinci anahtar: aynı saniyede üretilen iki bildirim
    (bir tarama turu bunu rahatlıkla yapar) `created_at` ile kararlı biçimde
    sıralanmaz ve sayfalar arasında kayıt tekrarlanabilir ya da atlanabilir.

    BACKLOG G2 — `tur`/`watch_id` süzgeçleri `LIMIT/OFFSET`TEN ÖNCE
    uygulanır (SQL WHERE her zaman böyle çalışır): sayfalama SÜZÜLMÜŞ
    kümeye göredir, yoksa "sayfa 2"de süzgeçle hiç eşleşmeyen kayıtlar
    sayılmış olur ve sayfa eksik dönerdi.
    """
    q = db.query(Alert).filter(Alert.user_id == kullanici.id)
    if sadece_okunmamis:
        q = q.filter(Alert.okundu.is_(False))
    if tur:
        q = q.filter(Alert.tur.in_(tur))
    if watch_id is not None:
        q = q.filter(Alert.watch_id == watch_id)
    return (q.order_by(Alert.created_at.desc(), Alert.id.desc())
            .offset(max(0, offset))
            .limit(min(max(1, limit), AZAMI_LIMIT))
            .all())


def okunmamis_sayisi(db: Session, kullanici: User) -> int:
    return (db.query(Alert)
            .filter(Alert.user_id == kullanici.id, Alert.okundu.is_(False))
            .count())


def okundu_isaretle(db: Session, kullanici: User, uyari_id: int) -> bool:
    a = (db.query(Alert)
         .filter(Alert.id == uyari_id, Alert.user_id == kullanici.id)
         .one_or_none())
    if a is None:
        return False
    a.okundu = True
    db.commit()
    return True


def hepsini_okundu_isaretle(db: Session, kullanici: User) -> int:
    n = (db.query(Alert)
         .filter(Alert.user_id == kullanici.id, Alert.okundu.is_(False))
         .update({"okundu": True}))
    db.commit()
    return n
