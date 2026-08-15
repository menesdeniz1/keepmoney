"""hesap yasam dongusu ve uyari yabanci anahtar kurallari

İki iş yapıyor:

1. `users`a parola sıfırlama / e-posta doğrulama sütunları. Token'lar
   HASH'lenmiş saklanıyor (bkz. guvenlik.token_hashle).

2. `alerts` yabancı anahtarlarına silme kuralları:
     user_id  → ON DELETE CASCADE    (hesap silinince uyarılar da gider)
     watch_id → ON DELETE SET NULL   (izleme silinse de uyarı geçmişi kalır)

   İkincisi bir HATA DÜZELTMESİ: kural yokken Postgres'te "takipten çıkar",
   o üründen bir kez bile uyarı almış her kullanıcı için yabancı anahtar
   ihlaliyle patlıyordu. SQLite yabancı anahtarları varsayılan olarak
   zorlamadığı için testler bunu görmüyordu.

Otomatik üretilen sürüm elle düzeltildi:
  • `drop_constraint(None, ...)` Postgres'te çalışmaz — kısıtın gerçek adı
    gerekir. SQLite'ta kısıtın adı yoktur; orada tablo yeniden kurulur.
  • `eposta_dogrulandi` NOT NULL olduğu için `server_default` şart:
    mevcut satırlara yazılacak bir değer olmadan ALTER başarısız olur.

Revision ID: f421f31ea3c8
Revises: b3b2695d9384
Create Date: 2026-08-15 15:53:52.398390

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f421f31ea3c8'
down_revision: str | Sequence[str] | None = 'b3b2695d9384'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Postgres'in otomatik ürettiği kısıt adları.
FK_KULLANICI = "alerts_user_id_fkey"
FK_IZLEME = "alerts_watch_id_fkey"


def _alerts_hedef_tablo(watch_ondelete: str | None,
                        user_ondelete: str | None) -> sa.Table:
    """SQLite batch modunun tabloyu yeniden kurarken kullanacağı tanım.

    Göç dosyaları uygulama modellerini İÇE AKTARMAZ: model zamanla değişir,
    göç ise yazıldığı andaki şemayı temsil etmelidir.
    """
    # İndeksler AÇIKÇA yazılır. Sütun üzerindeki `index=True` batch modunun
    # yeniden kurduğu tabloya taşınmıyor; indeksler sessizce kayboluyordu
    # (`alembic check` yakaladı). Tablo yeniden kurulurken eski indeksler de
    # gittiği için burada tam liste bulunmalı.
    return sa.Table(
        "alerts",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("users.id", ondelete=user_ondelete),
                  nullable=False),
        sa.Column("watch_id", sa.Integer,
                  sa.ForeignKey("watches.id", ondelete=watch_ondelete),
                  nullable=True),
        sa.Column("tur", sa.String, nullable=False),
        sa.Column("baslik", sa.String, nullable=False),
        sa.Column("mesaj", sa.String, nullable=False),
        sa.Column("okundu", sa.Boolean),
        sa.Column("telegram_gonderildi", sa.Boolean),
        sa.Column("created_at", sa.DateTime),
        sa.Index("ix_alerts_user_id", "user_id"),
        sa.Index("ix_alerts_telegram_gonderildi", "telegram_gonderildi"),
        sa.Index("ix_alerts_created_at", "created_at"),
    )


def _alerts_fk_uygula(watch_ondelete: str | None,
                      user_ondelete: str | None) -> None:
    if op.get_bind().dialect.name == "sqlite":
        # SQLite ALTER ile kısıt değiştiremez; batch tabloyu yeniden kurar.
        # `recreate="always"` ŞART: hiç işlem verilmediğinde batch varsayılan
        # olarak yeniden kurmayı ATLAR ve kısıtlar eski hâliyle kalır —
        # göç sessizce hiçbir şey yapmamış olur (`alembic check` yakaladı).
        with op.batch_alter_table(
            "alerts",
            copy_from=_alerts_hedef_tablo(watch_ondelete, user_ondelete),
            recreate="always",
        ):
            pass
        return

    op.drop_constraint(FK_KULLANICI, "alerts", type_="foreignkey")
    op.drop_constraint(FK_IZLEME, "alerts", type_="foreignkey")
    op.create_foreign_key(FK_KULLANICI, "alerts", "users", ["user_id"], ["id"],
                          ondelete=user_ondelete)
    op.create_foreign_key(FK_IZLEME, "alerts", "watches", ["watch_id"], ["id"],
                          ondelete=watch_ondelete)


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("users", schema=None) as b:
        b.add_column(sa.Column("parola_sifirlama_hash", sa.String(), nullable=True))
        b.add_column(sa.Column("parola_sifirlama_biter", sa.DateTime(), nullable=True))
        # server_default ŞART: NOT NULL sütun mevcut satırlara bir değer
        # yazılmadan eklenemez.
        b.add_column(sa.Column("eposta_dogrulandi", sa.Boolean(),
                               nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("eposta_dogrulama_hash", sa.String(), nullable=True))
        b.add_column(sa.Column("eposta_dogrulama_biter", sa.DateTime(), nullable=True))
        b.create_index(b.f("ix_users_parola_sifirlama_hash"),
                       ["parola_sifirlama_hash"], unique=False)
        b.create_index(b.f("ix_users_eposta_dogrulama_hash"),
                       ["eposta_dogrulama_hash"], unique=False)

    _alerts_fk_uygula(watch_ondelete="SET NULL", user_ondelete="CASCADE")


def downgrade() -> None:
    """Downgrade schema."""
    _alerts_fk_uygula(watch_ondelete=None, user_ondelete=None)

    with op.batch_alter_table("users", schema=None) as b:
        b.drop_index(b.f("ix_users_eposta_dogrulama_hash"))
        b.drop_index(b.f("ix_users_parola_sifirlama_hash"))
        b.drop_column("eposta_dogrulama_biter")
        b.drop_column("eposta_dogrulama_hash")
        b.drop_column("eposta_dogrulandi")
        b.drop_column("parola_sifirlama_biter")
        b.drop_column("parola_sifirlama_hash")
