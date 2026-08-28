"""izleme: yüzde eşiği ve yeniden kurma süresi

BACKLOG E1 — "%15 düşerse haber ver" mutlak rakamı bilmeyen kullanıcının
doğal ifadesi; şu ana kadar yalnızca mutlak hedef fiyat vardı. `watches`
tablosuna iki sütun: `dusus_yuzdesi` (kullanıcının seçtiği eşik, 1-90) ve
`yeniden_kur_gun` (rearm süresi). HESAP burada YAPILMAZ — worker'ın yüzde
kuralını uygulaması E2'nin işi, arayüz kontrolü E3'ün.

BATCH_ALTER_TABLE KULLANILMADI — bilinçli, `c7e5a92f1b4d` (ürün bağlam
sütunları) ile AYNI gerekçe: iki sütun da nullable, FK'siz, indekssiz.
SQLite'ın native ALTER TABLE ADD/DROP COLUMN'u bunu tam destekliyor,
tabloyu yeniden KURMUYOR — yani `a3c81f47b2d9`'daki CASCADE riski (FK'li
sütun düşürme, orada `batch_alter_table` zorunluydu) burada YOK. Test
(`test_gocler.py`) bunu gerçek veriyle doğruluyor.

Revision ID: a9edb33fc2b8
Revises: c7e5a92f1b4d
Create Date: 2026-08-29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9edb33fc2b8"
down_revision: str | Sequence[str] | None = "c7e5a92f1b4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("watches", sa.Column("dusus_yuzdesi", sa.Integer(), nullable=True))
    op.add_column("watches", sa.Column("yeniden_kur_gun", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("watches", "yeniden_kur_gun")
    op.drop_column("watches", "dusus_yuzdesi")
