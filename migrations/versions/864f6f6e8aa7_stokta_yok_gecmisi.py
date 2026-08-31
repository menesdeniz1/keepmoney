"""stokta yok geçmişi: price_readings.fiyat nullable + stokta_var

BACKLOG B4 — grafikte "fiyat sabit kaldı" ile "ürün stokta yoktu" aynı
görünüyordu; ikisi de aynı şeydi: o günlere ait hiçbir satır yok. Worker
STOKTA_YOK okuduğunda (worker.py: "sayfa sağlam, ürünün o an fiyatı yok")
şimdiye kadar `price_readings`e HİÇ satır yazmıyordu.

`fiyat` NULLABLE olur, yeni `stokta_var` sütunu (varsayılan `True`) eklenir.
Worker artık STOKTA_YOK'ta `fiyat=None, stokta_var=False` satırı yazacak;
grafik bunu çizgiyi KESEN bir boşluk olarak gösterir.

`batch_alter_table` GEREKLİ (emsal: a3c81f47b2d9): SQLite `ALTER COLUMN`
desteklemiyor, `fiyat`in NOT NULL kısıtını kaldırmak tabloyu yeniden
kurmayı gerektiriyor. Bu tabloya işaret eden hiçbir `ON DELETE CASCADE`
YOK (`price_readings.id`yi yabancı anahtar olarak kullanan başka tablo
yok) — yani a3c81f47b2d9'daki CASCADE-veri-kaybı riski burada söz konusu
değil, Alembic'in otomatik satır kopyalaması yeterli. Yine de gerçek
veriyle doğrulanıyor (tests/test_gocler.py, §5.19 gerekçesiyle:
`alembic check` şemayı doğrular, veriyi değil).

Eski satırların hepsi fiyatlıydı — `server_default` ile hepsi `stokta_var
= True` alır, geçmiş "stoktaydı" sayılmaya devam eder (B4 kabul ölçütü).

Revision ID: 864f6f6e8aa7
Revises: a9edb33fc2b8
Create Date: 2026-08-31
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "864f6f6e8aa7"
down_revision: str | Sequence[str] | None = "a9edb33fc2b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("price_readings", schema=None) as batch:
        batch.add_column(sa.Column("stokta_var", sa.Boolean(), nullable=False,
                                   server_default=sa.true()))
        batch.alter_column("fiyat", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    # `fiyat IS NULL` satırlar SADECE bu göçten sonra yazılabilir (STOKTA_YOK
    # okumaları) — göçten ÖNCE hiç var olamazlardı, worker o dalda satır hiç
    # eklemiyordu. `fiyat` yeniden NOT NULL olacağı için bu satırlar
    # SİLİNİR: geri alma, öncesindeki davranışa (o okumalar hiç
    # yazılmıyordu) dönüyor — kayıp yalnızca bu göçün YENİ eklediği
    # satırlarla sınırlı, öncesinde zaten var olan hiçbir fiyat kaybolmaz.
    baglanti = op.get_bind()
    baglanti.execute(sa.text("DELETE FROM price_readings WHERE fiyat IS NULL"))
    with op.batch_alter_table("price_readings", schema=None) as batch:
        batch.alter_column("fiyat", existing_type=sa.Float(), nullable=False)
        batch.drop_column("stokta_var")
