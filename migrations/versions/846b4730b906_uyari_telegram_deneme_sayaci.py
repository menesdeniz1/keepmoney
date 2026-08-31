"""uyari telegram deneme sayaci

`alerts.telegram_deneme` — bir uyarının kaç kez iletilmeye çalışıldığı.

NEDEN (ölçüldü): gönderici başarısız uyarıyı SONSUZA KADAR yeniden
deniyordu ve sorgu `created_at`e göre sıralı + `limit`li. Bir kullanıcı
botu bloklarsa Telegram kalıcı hata döner, o uyarılar hiç temizlenmez ve
zamanla kuyruğun başını doldurur. 30 tıkalı uyarı + 1 yeni uyarıyla 5 tur
koşuldu: yeni uyarı BİR KEZ BİLE denenmedi. Yani tek bir kullanıcının
davranışı, ürünün ana değer teslimini HERKES için durduruyordu.

BATCH KULLANILMIYOR — bkz. `c5f2a71e8d40`'ın gerekçesi: `batch_alter_table`
SQLite'ta tabloyu DROP+yeniden kuruyor ve gerçek veri varken yabancı
anahtar kısıtı patlıyor. İki yönde de yerel `ALTER TABLE` (SQLite 3.35+,
Postgres zaten destekliyor).

`server_default="0"` ŞART: NOT NULL sütun mevcut satırlara bir değer
yazılmadan eklenemez. Bekleyen uyarılar 0'dan başlar, yani göç kimsenin
bildirimini düşürmez.

Revision ID: 846b4730b906
Revises: c5f2a71e8d40
Create Date: 2026-08-31 22:05:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '846b4730b906'
down_revision: str | Sequence[str] | None = 'c5f2a71e8d40'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("telegram_deneme", sa.Integer(),
                                      nullable=False, server_default="0"))


def downgrade() -> None:
    """Sütun düşer. Geri alma, sonsuz yeniden deneme davranışını da geri
    getirir — kuyruk tıkanması yeniden mümkün olur."""
    op.drop_column("alerts", "telegram_deneme")
