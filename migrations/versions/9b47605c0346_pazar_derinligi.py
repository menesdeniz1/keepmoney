"""pazar derinligi: satici sayisi ve 2. en ucuz fiyat

Toplayıcı kaynaklarda (akakçe, cimri) aynı ürünü satan mağazaların sayısı ve
ikinci en ucuz fiyat saklanır. Bu, GEÇMİŞİ OLMAYAN ürünün tek savunmasıdır:
koruma katmanının diğer ölçütleri son iyi fiyata bakıyor ve yeni üründe öyle
bir fiyat yok. "En ucuz 4.000 TL ama ikincisi 52.000 TL" tablosu, geçmiş
olmadan da o 4.000'in gerçek olmadığını söyler.

İki kolon da nullable: toplayıcı olmayan kaynaklarda "pazar" diye bir kavram
yok ve orayı 0 ile doldurmak "hiç satıcı yok" gibi okunurdu.

Revision ID: 9b47605c0346
Revises: f421f31ea3c8
Create Date: 2026-08-17
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9b47605c0346"
down_revision: str | Sequence[str] | None = "f421f31ea3c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sources",
                  sa.Column("satici_sayisi", sa.Integer(), nullable=True))
    op.add_column("sources",
                  sa.Column("ikinci_fiyat", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("sources", "ikinci_fiyat")
    op.drop_column("sources", "satici_sayisi")
