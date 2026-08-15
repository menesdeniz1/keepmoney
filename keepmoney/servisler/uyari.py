"""Uyarı (bildirim) use-case'leri."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Alert, User

VARSAYILAN_LIMIT = 50


def listele(db: Session, kullanici: User, sadece_okunmamis: bool = False,
            limit: int = VARSAYILAN_LIMIT) -> list[Alert]:
    q = db.query(Alert).filter(Alert.user_id == kullanici.id)
    if sadece_okunmamis:
        q = q.filter(Alert.okundu.is_(False))
    return q.order_by(Alert.created_at.desc()).limit(limit).all()


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
