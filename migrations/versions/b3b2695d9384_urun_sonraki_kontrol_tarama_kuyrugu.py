"""urun sonraki_kontrol tarama kuyrugu

Tarama sırası artık `son_kontrol + kontrol_araligi_dk` hesabıyla Python'da
değil, indeksli tek sütun karşılaştırmasıyla SQL'de bulunuyor.

BACKFILL YOK — bilerek: sütun tüm satırlarda NULL kalır ve NULL "sırası
gelmiş" demektir. Yani göç sonrası ilk turlarda her ürün bir kez taranır.
Zararsız, çünkü tur başına ürün sayısı sınırlı (TUR_BASINA_URUN) ve host
throttle devrede; kuyruk kendiliğinden normale oturur. Alternatif
(son_kontrol + aralık ile doldurmak) veritabanına özgü tarih aritmetiği
gerektirirdi — SQLite ve PostgreSQL'de farklı yazılırdı.

Revision ID: b3b2695d9384
Revises: 1d1132452ebc
Create Date: 2026-08-15 13:55:36.966629

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3b2695d9384'
down_revision: str | Sequence[str] | None = '1d1132452ebc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sonraki_kontrol', sa.DateTime(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_products_sonraki_kontrol'), ['sonraki_kontrol'],
            unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_products_sonraki_kontrol'))
        batch_op.drop_column('sonraki_kontrol')
