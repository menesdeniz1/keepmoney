"""TL parse testleri — Türk e-ticaret sitelerinden toplanmış gerçek biçimler."""
import pytest

from keepmoney.fiyat import kisa_tl, parse_tl, tl, yuzde


@pytest.mark.parametrize("girdi,beklenen", [
    ("53.599 TL", 53599.0),          # nokta = binlik
    ("53.599,50 TL", 53599.5),       # virgül = ondalık
    ("599.5 TL", 599.5),             # nokta = ondalık (3 hane değil)
    ("2.798,80 ₺", 2798.80),
    ("2,399.00 TL", 2399.00),        # EN yerelli site
    ("1.053.599", 1053599.0),
    ("1,053,599", 1053599.0),
    ("53599,50", 53599.5),
    ("53,599", 53599.0),             # virgül + 3 hane = binlik
    ("14799.0", 14799.0),
    ("  1.299,00 TL  ", 1299.0),
    ("Fiyat: 4.750 TL (KDV dahil)", 4750.0),
    (1499, 1499.0),
    (1499.9, 1499.9),
])
def test_gecerli_fiyatlar(girdi, beklenen):
    assert parse_tl(girdi) == pytest.approx(beklenen)


@pytest.mark.parametrize("girdi", [
    None, "", "   ", "TL", "fiyat yok", "—", "abc",
    0, -100, 999_999_999_999,        # makul aralık dışı
])
def test_gecersiz_fiyatlar(girdi):
    assert parse_tl(girdi) is None


def test_tl_bicimleme():
    assert tl(26450.5) == "26.450,50 TL"
    assert tl(None) == "—"


def test_kisa_tl_ondaliksiz():
    assert kisa_tl(26450.5) == "26.450₺"
    assert kisa_tl(None) == "—"


def test_yuzde_yon_isareti():
    assert yuzde(-4.23) == "↓%4,2"
    assert yuzde(2.1) == "↑%2,1"
