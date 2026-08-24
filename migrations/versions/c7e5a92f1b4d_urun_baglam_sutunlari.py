"""ürün bağlam sütunları: analiz motoru artık atmıyor, saklıyor

`analiz.fiyat_baglami()` dip/ucuz/pahalı sinyalini, 90 günün dibini, medyanı,
yüzdeliği ve kaç günlük geçmişe dayandığını üretiyor. `worker.py` her
taramada bunu hesaplıyor, uyarı kararı için kullanıyor ve ATIYORDU —
`Product` tablosunda saklayan sütun yoktu. Sonuç: ürünün en değerli tarafı,
en çok bakılan ekranda (panel listesi) hiç görünmüyordu, çünkü liste ucu
ürün başına ayrı bir geçmiş sorgusu açmadan sinyali gösteremiyordu.

`sahte_indirim` ve `trend_yonu` BİLEREK BURADA DEĞİL: kart bunları
göstermiyor, gösteren detay sayfası zaten canlı hesaplıyor. Gereksiz sütun
yazma maliyeti olurdu.

BATCH_ALTER_TABLE KULLANILMADI — bilinçli. Emsal: 9b47605c0346 (pazar
derinliği) aynı şekilde `sources`'a iki nullable sütunu düz `add_column` ile
ekledi ve `sources`'ın da kendi çocuk tablosu (`price_readings`) var, orada
da veri kaybı olmadı. Buradaki sütunlar da nullable, FK'siz, indekssiz —
SQLite'ın native ALTER TABLE ADD/DROP COLUMN'u bunu tam destekliyor, tabloyu
yeniden kurmuyor. `a3c81f47b2d9`'daki tuzak (§5.19) farklı bir durumdandı:
orada düşürülen `set_id` bir FOREIGN KEY taşıyordu ve SQLite FK'li sütun
düşürmeyi native desteklemiyor — o yüzden orada `batch_alter_table` (tablo
yeniden kurma) zorunluydu ve CASCADE riski oradan geliyordu. Burada öyle bir
zorunluluk yok; test bunu gerçek veriyle doğruluyor.

Revision ID: c7e5a92f1b4d
Revises: a3c81f47b2d9
Create Date: 2026-08-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7e5a92f1b4d"
down_revision: str | Sequence[str] | None = "a3c81f47b2d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("sinyal", sa.String(), nullable=True))
    op.add_column("products", sa.Column("dip90", sa.Float(), nullable=True))
    op.add_column("products", sa.Column("medyan90", sa.Float(), nullable=True))
    op.add_column("products", sa.Column("yuzdelik", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("gecmis_gun", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("baglam_ts", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "baglam_ts")
    op.drop_column("products", "gecmis_gun")
    op.drop_column("products", "yuzdelik")
    op.drop_column("products", "medyan90")
    op.drop_column("products", "dip90")
    op.drop_column("products", "sinyal")
