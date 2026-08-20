"""fiyat geçmişi ve uyarı listesi için bileşik indeks

ÖLÇÜM (SQLite, `EXPLAIN QUERY PLAN`):

    SELECT ts, fiyat FROM price_readings WHERE product_id=? ORDER BY ts
      SEARCH price_readings USING INDEX ix_price_readings_product_id
      USE TEMP B-TREE FOR ORDER BY          ← her çağrıda bellekte sıralama

    SELECT * FROM alerts WHERE user_id=? ORDER BY created_at DESC
      SEARCH alerts USING INDEX ix_alerts_user_id
      USE TEMP B-TREE FOR ORDER BY

Bu iki desen ürünün en sıcak okuma yolları: fiyat geçmişi hem grafikte hem
HER tarama turunda okunuyor (worker analiz ve bir sonraki kontrol aralığı
için `_okuma_gecmisi` çağırıyor), uyarı listesi de panel her açıldığında.

Tek sütunluk indeksler KALDIRILIYOR, bileşiğin içinde eriyorlar: en soldaki
sütun aynı işi görür. İkisini birden tutmak, sürekli büyüyen bir tabloya
(fiyat geçmişi ürünün asıl değeri ve hiç silinmiyor) her INSERT'te ikinci
bir ağaç bakımı yüklerdi.

SIRA ÖNEMLİ: önce yeni indeks kurulur, sonra eskisi düşer. Tersi, üretimde
(Postgres) tablonun bir süre indekssiz kalması demektir.

`batch_alter_table` KULLANILMIYOR: o, SQLite'ın ALTER TABLE kısıtları için
var ve tabloyu yeniden inşa edebiliyor. İndeks işlemlerini SQLite de Postgres
de doğrudan destekliyor; en değerli tabloyu kopyalama riskine sokmanın
sebebi yok.

Revision ID: 28f883ebaff7
Revises: 9b47605c0346
Create Date: 2026-08-21
"""
from collections.abc import Sequence

from alembic import op

revision: str = "28f883ebaff7"
down_revision: str | Sequence[str] | None = "9b47605c0346"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_price_readings_product_ts", "price_readings",
                    ["product_id", "ts"], unique=False)
    op.drop_index("ix_price_readings_product_id", table_name="price_readings")

    op.create_index("ix_alerts_user_created", "alerts",
                    ["user_id", "created_at"], unique=False)
    op.drop_index("ix_alerts_user_id", table_name="alerts")


def downgrade() -> None:
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"], unique=False)
    op.drop_index("ix_alerts_user_created", table_name="alerts")

    op.create_index("ix_price_readings_product_id", "price_readings",
                    ["product_id"], unique=False)
    op.drop_index("ix_price_readings_product_ts", table_name="price_readings")
