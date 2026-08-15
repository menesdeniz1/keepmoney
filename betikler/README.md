# İşletim betikleri

## Yedekleme

```bash
KEEPMONEY_VERITABANI_URL=... ./betikler/yedekle.sh
```

SQLite ve PostgreSQL için tek betik. Her ikisinde de yedek **doğrulanır** —
doğrulanmamış yedek, yedek değil temennidir.

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `YEDEK_DIZIN` | `./yedekler` | Başka bir makineye/nesne deposuna bağla |
| `SAKLAMA_GUN` | `14` | Bundan eski yedekler silinir |

Crontab (her gece 03:30):

```
30 3 * * * cd /opt/keepmoney && ./betikler/yedekle.sh >> /var/log/km-yedek.log 2>&1
```

**Yedeği aynı sunucuda tutmak yedek değildir** — disk arızası ikisini birden
götürür.

## Geri yükleme

```bash
KEEPMONEY_VERITABANI_URL=... ./betikler/geri-yukle.sh yedekler/keepmoney-20260815-033000.dump
```

SQLite tarafında yedek, üzerine yazmadan **önce** bütünlük kontrolünden
geçer: bozuk bir yedekle çalışan veritabanının üzerine yazmak tek felaketi
ikiye çıkarır.

### Tatbikat şart

Denenmemiş geri yükleme prosedürü, felaket anında ilk kez denenen
prosedürdür. **Ayda bir** boş bir veritabanına geri yükleyip satır
sayılarını karşılaştır:

```bash
runuser -u postgres -- psql -c "CREATE DATABASE km_tatbikat;"
KEEPMONEY_VERITABANI_URL=postgresql+psycopg://.../km_tatbikat \
  ONAYSIZ=1 ./betikler/geri-yukle.sh <son-yedek>
# satır sayıları üretimle uyuşuyor mu?
```

`ONAYSIZ=1` yalnızca otomatik tatbikat içindir; elle çalıştırmada onay sorulur.

## Neden bu kadar önemli

Bu üründe asıl değer **fiyat geçmişidir** ve geçmiş yeniden üretilemez.
Kod kaybolursa yeniden yazılır, sunucu kaybolursa yenisi kurulur; iki yıllık
fiyat hafızası kaybolursa geri getirmenin yolu yoktur.
