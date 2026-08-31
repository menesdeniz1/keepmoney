"""oturum surumu: parola degisince eski token'lar dussun

`users.oturum_surumu` — JWT'deki `ver` bu sayaçla eşleşmiyorsa token
reddedilir. Parola sıfırlanınca sayaç artar, o ana kadarki bütün oturumlar
düşer.

NEDEN (ölçüldü): JWT durumsuzdur. Parola sıfırlandıktan sonra eski oturum
`/api/auth/ben`den hâlâ 200 alıyordu — hesabı ele geçirilmiş kullanıcının
parolasını değiştirmesi saldırganı DIŞARI ATMIYORDU (OWASP ASVS 3.3.x).

── BATCH KULLANILMIYOR, VE BU DOSYANIN ASIL DERSİ BU ──────────────

`op.batch_alter_table` SQLite'ta tabloyu YENİDEN KURAR (yeni tablo → kopyala
→ `DROP TABLE users` → yeniden adlandır). ÖLÇÜLDÜ: gerçek veri varken bu
adım şununla patlıyor:

    sqlite3.IntegrityError: FOREIGN KEY constraint failed

çünkü `PRAGMA foreign_keys=ON` (keepmoney/db.py) ve `watches.user_id`,
`watch_sets.user_id` `users.id`e NO ACTION ile bağlı — `DROP TABLE users`
o satırları yetim bırakacağı için reddediliyor. `alerts.user_id` ise
CASCADE: kısıt hatası olmasaydı uyarı geçmişi SESSİZCE silinecekti.

Bu, §1'deki göç tuzağının `users` tablosundaki hâli ve BU GÖÇE KADAR
KİMSE ÇARPMAMIŞTI: önceki `users` göçü (f421f31ea3c8) yalnızca sütun
EKLİYOR, SQLite bunu `ALTER TABLE ADD COLUMN` ile yerel olarak yapıyor ve
tabloyu yeniden kurmuyor. Sorun DÜŞÜRMEDE ortaya çıkıyor.

ÇÖZÜM: iki yönde de YEREL `ALTER TABLE`. SQLite 3.35+ `DROP COLUMN`
destekliyor (Python 3.12 ile gelen sürüm 3.4x), Postgres zaten destekliyor.
Tablo yeniden kurulmadığı için hiçbir yabancı anahtar tetiklenmiyor.

`server_default="0"` ŞART: NOT NULL sütun, mevcut satırlara yazılacak bir
değer olmadan eklenemez. Mevcut kullanıcılar 0'da başlar; token'ında `ver`
olmayan eski oturumlar da 0 sayılır (guvenlik.jwt_kimlik) — yani bu göç
kimsenin oturumunu kapatmaz. İlk parola sıfırlamasında sayaç 1 olur ve o
kullanıcının eski token'ları tam o anda geçersizleşir.

Revision ID: c5f2a71e8d40
Revises: 864f6f6e8aa7
Create Date: 2026-08-31 17:40:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c5f2a71e8d40'
down_revision: str | Sequence[str] | None = '864f6f6e8aa7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("oturum_surumu", sa.Integer(),
                                     nullable=False, server_default="0"))


def downgrade() -> None:
    """Sütun düşer; açık oturumlar etkilenmez.

    Geri alma VERİ KAYBI DEĞİLDİR ama GÜVENLİK KAYBIDIR: sayaç silinince
    daha önce iptal edilmiş token'lar (süresi dolmamışsa) yeniden geçerli
    olur. Yalnızca dağıtım geri sarılırken kullanılmalı.
    """
    op.drop_column("users", "oturum_surumu")
