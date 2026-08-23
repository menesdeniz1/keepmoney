"""çoklu set üyeliği: Watch.set_id → set_uyeleri ara tablosu

Bir ürün yalnızca TEK sete girebiliyordu (`Watch.set_id`). Bu belgelenmiş bir
karar değildi — en basit hâli önce yazılmış, sonra dokunulmamıştı. Gerçek
kullanımda aynı ekran kartı hem "PC Toplama" hem "Kara Cuma" listesinde
olabilir; kullanıcıyı ikisinden birini seçmeye zorlamak modelin eksikliğiydi.

VERİ KORUNUR: mevcut `set_id` değerleri ara tabloya satır olarak taşınır ve
ancak ondan SONRA sütun düşürülür. Sıra tersine olsaydı üyelikler geri
alınamaz biçimde kaybolurdu.

`batch_alter_table` BURADA GEREKLİ (indeks göçünün aksine): SQLite sütun
düşürmeyi doğrudan desteklemiyor, tabloyu yeniden kurmak gerekiyor. Alembic
bunu veriyi kopyalayarak yapıyor — bu yüzden veri taşıma adımı önce koşuyor.

Geri alma da veriyi korur: her izleme için ara tablodaki İLK üyelik
`set_id`ye yazılır. Çoklu üyelik tek sütuna sığmadığı için fazlası düşer —
downgrade'in kayıpsız olamayacağı yer burası ve bilinçli.

Revision ID: a3c81f47b2d9
Revises: 28f883ebaff7
Create Date: 2026-08-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c81f47b2d9"
down_revision: str | Sequence[str] | None = "28f883ebaff7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    baglanti = op.get_bind()

    # 1) Üyelikler ÖNCE BELLEĞE alınır.
    #
    # ÖLÇÜLDÜ — ilk deneme veri kaybetti: ara tablo önce kurulup satırlar
    # oraya yazılmış, sonra `batch_alter_table` çalışmıştı. SQLite sütun
    # düşürmeyi desteklemediği için Alembic o adımda `watches` tablosunu
    # DROP edip yeniden kuruyor; yabancı anahtarlar açık olduğu için
    # (bkz. db.py) `set_uyeleri` üzerindeki ON DELETE CASCADE tetiklendi ve
    # yeni taşınan satırlar SESSİZCE silindi. Göç "başarılı" göründü,
    # üyelikler gitti.
    #
    # Bu yüzden sıra: oku → sütunu düşür → tabloyu kur → yaz. Veri hiçbir
    # anda silinebilecek bir tabloda beklemiyor.
    uyelikler = list(baglanti.execute(sa.text(
        "SELECT id, set_id FROM watches WHERE set_id IS NOT NULL")))

    # 2) Sütun düşer (bu adım `watches`i yeniden kurabilir).
    with op.batch_alter_table("watches", schema=None) as batch:
        batch.drop_column("set_id")

    # 3) Ara tablo kurulur.
    op.create_table(
        "set_uyeleri",
        sa.Column("watch_id", sa.Integer(),
                  sa.ForeignKey("watches.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("set_id", sa.Integer(),
                  sa.ForeignKey("watch_sets.id", ondelete="CASCADE"),
                  primary_key=True),
    )

    # 4) Üyelikler geri yazılır.
    if uyelikler:
        baglanti.execute(
            sa.text("INSERT INTO set_uyeleri (watch_id, set_id) "
                    "VALUES (:watch_id, :set_id)"),
            [{"watch_id": w, "set_id": s} for w, s in uyelikler],
        )


def downgrade() -> None:
    baglanti = op.get_bind()

    # AYNI TUZAK TERS YÖNDE, testle yakalandı (tests/test_gocler.py):
    # `add_column` da SQLite'ta tabloyu yeniden kuruyor, yani `watches`
    # DROP ediliyor ve `set_uyeleri` satırları CASCADE ile siliniyor. Sonra
    # onlardan okumaya çalışan UPDATE her yere NULL yazıyordu.
    #
    # Bu yüzden üyelikler ÖNCE belleğe alınır. Çoklu üyelik tek sütuna
    # sığmadığı için izleme başına en küçük `set_id` seçilir; fazlası düşer.
    # Kayıpsız geri alma bu şemada mümkün değil ve bu bilinçli.
    eslesme = dict(baglanti.execute(sa.text(
        "SELECT watch_id, MIN(set_id) FROM set_uyeleri GROUP BY watch_id"
    )).all())

    op.drop_table("set_uyeleri")

    with op.batch_alter_table("watches", schema=None) as batch:
        batch.add_column(sa.Column("set_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_watches_set_id", "watch_sets",
                                 ["set_id"], ["id"])

    if eslesme:
        baglanti.execute(
            sa.text("UPDATE watches SET set_id = :set_id WHERE id = :watch_id"),
            [{"watch_id": w, "set_id": s} for w, s in eslesme.items()],
        )
