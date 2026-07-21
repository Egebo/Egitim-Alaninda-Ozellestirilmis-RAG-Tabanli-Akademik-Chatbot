"""Uygulama genelinde tutarli log formati saglayan merkezi logging kurulumu.

`app.py` açılışında bir kez `setup_logging()` çağrılır; her modül kendi
logger'ını `logging.getLogger(__name__)` ile alır (bkz. `core/lazy_imports.py`,
`core/database.py`, `services/chat.py`, `services/crawler.py`). `LOG_LEVEL`
ortam değişkeniyle seviye ayarlanabilir (varsayılan INFO).
"""
import logging
import os


def setup_logging():
    seviye_adi = os.environ.get('LOG_LEVEL', 'INFO').upper()
    seviye = getattr(logging, seviye_adi, logging.INFO)
    logging.basicConfig(
        level=seviye,
        format='%(asctime)s %(levelname)-8s %(name)s: %(message)s',
        datefmt='%H:%M:%S',
    )
