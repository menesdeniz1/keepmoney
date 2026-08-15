"""`python -m keepmoney.bot` — botu uzun yoklama ile çalıştırır."""
import asyncio
import logging

from .uygulama import calistir

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    asyncio.run(calistir())
