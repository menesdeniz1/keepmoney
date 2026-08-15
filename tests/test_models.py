"""Şema testleri — asıl amaç: küresel ürün / kişisel izleme ayrımının
gerçekten işlediğini kanıtlamak."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from keepmoney.db import Base
from keepmoney.models import (
    Alert,
    PriceReading,
    Product,
    Source,
    User,
    Watch,
    WatchSet,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def kullanici(db, email):
    u = User(email=email, password_hash="x")
    db.add(u)
    db.commit()
    return u


def test_iki_kullanici_ayni_urunu_paylasir(db):
    """Modelin varlık sebebi: aynı link iki kez taranmaz."""
    p = Product(ad="RTX 5070 Ti")
    db.add(p)
    db.commit()
    db.add(Source(product_id=p.id, url="https://magaza.com/rtx", host="magaza.com"))
    db.commit()

    a, b = kullanici(db, "a@x.com"), kullanici(db, "b@x.com")
    db.add_all([Watch(user_id=a.id, product_id=p.id, hedef_fiyat=50000),
                Watch(user_id=b.id, product_id=p.id, hedef_fiyat=45000)])
    db.commit()

    assert db.query(Source).count() == 1          # tek kaynak = tek tarama
    assert db.query(Watch).count() == 2           # ama iki farklı hedef
    assert len(p.watches) == 2


def test_gecmis_kuresel_yeni_kullanici_aninda_gorur(db):
    """Yeni kullanıcı ürünü eklediği an geçmiş grafiği dolu gelir —
    kişiye özel geçmişte ilk gün boş olurdu."""
    p = Product(ad="Kingston 32GB DDR5")
    db.add(p)
    db.commit()
    s = Source(product_id=p.id, url="https://m.com/ram", host="m.com")
    db.add(s)
    db.commit()
    for f in (26000, 25500, 24900):
        db.add(PriceReading(source_id=s.id, product_id=p.id, fiyat=f))
    db.commit()

    yeni = kullanici(db, "yeni@x.com")
    db.add(Watch(user_id=yeni.id, product_id=p.id))
    db.commit()

    gecmis = db.query(PriceReading).filter_by(product_id=p.id).all()
    assert len(gecmis) == 3


def test_ayni_url_iki_kez_eklenemez(db):
    p = Product(ad="Ürün")
    db.add(p)
    db.commit()
    db.add(Source(product_id=p.id, url="https://m.com/x", host="m.com"))
    db.commit()
    db.add(Source(product_id=p.id, url="https://m.com/x", host="m.com"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_kullanici_ayni_urunu_iki_kez_izleyemez(db):
    p = Product(ad="Ürün")
    u = kullanici(db, "a@x.com")
    db.add(p)
    db.commit()
    db.add(Watch(user_id=u.id, product_id=p.id))
    db.commit()
    db.add(Watch(user_id=u.id, product_id=p.id))
    with pytest.raises(IntegrityError):
        db.commit()


def test_urun_coklu_kaynak_tasir(db):
    """Çoklu kaynak = en ucuzu bulma yeteneği."""
    p = Product(ad="Ürün")
    db.add(p)
    db.commit()
    db.add_all([
        Source(product_id=p.id, url="https://akakce.com/u", host="akakce.com",
               toplayici=True, son_fiyat=1100),
        Source(product_id=p.id, url="https://a.com/u", host="a.com", son_fiyat=1200),
        Source(product_id=p.id, url="https://b.com/u", host="b.com", son_fiyat=1150),
    ])
    db.commit()
    db.refresh(p)
    assert len(p.sources) == 3
    assert min(s.son_fiyat for s in p.sources) == 1100


def test_set_butcesi_ve_uyeler(db):
    u = kullanici(db, "a@x.com")
    ws = WatchSet(user_id=u.id, ad="PC Toplama", hedef_butce=84000)
    db.add(ws)
    db.commit()

    toplam = 0
    for ad, fiyat in [("CPU", 12000), ("GPU", 50000), ("RAM", 26000)]:
        p = Product(ad=ad, guncel_fiyat=fiyat)
        db.add(p)
        db.commit()
        db.add(Watch(user_id=u.id, product_id=p.id, set_id=ws.id))
        toplam += fiyat
    db.commit()
    db.refresh(ws)

    assert len(ws.watches) == 3
    assert toplam == 88000
    assert toplam > ws.hedef_butce      # henüz hedefte değil


def test_kullanici_silinince_kisisel_veri_gider_urun_kalir(db):
    """Kullanıcı hesabını silince küresel fiyat geçmişi KAYBOLMAMALI."""
    u = kullanici(db, "a@x.com")
    p = Product(ad="Ürün")
    db.add(p)
    db.commit()
    s = Source(product_id=p.id, url="https://m.com/x", host="m.com")
    db.add(s)
    db.commit()
    db.add(PriceReading(source_id=s.id, product_id=p.id, fiyat=100))
    db.add(Watch(user_id=u.id, product_id=p.id))
    db.commit()

    db.delete(u)
    db.commit()

    assert db.query(Watch).count() == 0
    assert db.query(Product).count() == 1
    assert db.query(PriceReading).count() == 1


def test_telegram_chat_id_tekil(db):
    """İki hesap aynı Telegram chat'ini iddia edemez — bot gelen mesajı
    tek bir kullanıcıya çözebilmeli."""
    a = User(email="a@x.com", password_hash="x", telegram_chat_id="123")
    db.add(a)
    db.commit()
    db.add(User(email="b@x.com", password_hash="x", telegram_chat_id="123"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_alert_kaydi(db):
    u = kullanici(db, "a@x.com")
    db.add(Alert(user_id=u.id, tur="HEDEF", baslik="Fiyat düştü",
                 mesaj="Hedefin altına indi"))
    db.commit()
    a = db.query(Alert).one()
    assert a.okundu is False
