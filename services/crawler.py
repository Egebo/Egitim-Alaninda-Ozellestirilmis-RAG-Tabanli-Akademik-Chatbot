"""Web sitesi tarayıcı: sayfaları çeker, düz metne çevirir ve RAG'a belge olarak ekler."""
import os
import re
import time
import urllib.request
import urllib.robotparser
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser

from core.state import state
from core.lazy_imports import ensure_imports


class _HTMLTextExtractor(HTMLParser):
    SKIP_TAGS = {'script','style','noscript','head',
                 'nav','footer','aside','form','button','svg','iframe'}
    def __init__(self):
        super().__init__()
        self._stack = []; self._skip = False; self.texts = []
    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS: self._stack.append(tag); self._skip = True
    def handle_endtag(self, tag):
        if self._stack and self._stack[-1] == tag:
            self._stack.pop(); self._skip = bool(self._stack)
    def handle_data(self, data):
        if not self._skip:
            t = data.strip()
            if t: self.texts.append(t)
    def get_text(self): return ' '.join(self.texts)


def _html_to_text(html):
    p = _HTMLTextExtractor()
    try: p.feed(html)
    except: pass
    return re.sub(r'\s{3,}', '\n\n', p.get_text()).strip()


def _get_links(html, base_url):
    base_netloc = urlparse(base_url).netloc
    links = []
    class LP(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == 'a':
                href = dict(attrs).get('href','')
                if href:
                    abs_url = urljoin(base_url, href)
                    p = urlparse(abs_url)
                    if p.netloc == base_netloc:
                        links.append(p._replace(fragment='').geturl())
    lp = LP()
    try: lp.feed(html)
    except: pass
    return list(set(links))


def _website_to_rag_klasik(start_url, max_pages=30, delay=0.3, respect_robots=True, status_cb=None):
    def log(m):
        print(f'[CRAWLER] {m}')
        if status_cb: status_cb(m)

    parsed = urlparse(start_url)
    domain = parsed.netloc
    base = f"{parsed.scheme}://{domain}"
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; AcademicBot/1.0)'}

    rp = urllib.robotparser.RobotFileParser()
    if respect_robots:
        try: rp.set_url(f"{base}/robots.txt"); rp.read()
        except: pass

    queue, visited, skipped = [start_url], set(), 0
    texts = []

    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited: continue
        if respect_robots and not rp.can_fetch('*', url):
            skipped += 1; continue
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as r:
                ct = r.headers.get('Content-Type','')
                if 'text/html' not in ct: skipped += 1; continue
                html = r.read().decode('utf-8', errors='replace')
        except Exception as e:
            log(f'⚠️ {url}: {e}'); skipped += 1; continue

        visited.add(url)
        text = _html_to_text(html)
        if len(text) > 100:
            texts.append(f"\n\n{'='*60}\nKAYNAK: {url}\n{'='*60}\n{text}")

        for lnk in _get_links(html, url):
            if lnk not in visited and lnk not in queue:
                queue.append(lnk)

        log(f'✅ [{len(visited)}/{max_pages}] {url}')
        time.sleep(delay)

    if not texts:
        return {'crawled': 0, 'skipped': skipped, 'doc_name': None}

    combined = f"WEB SİTESİ: {start_url}\nTarih: {time.strftime('%Y-%m-%d %H:%M')}\n" + ''.join(texts)
    return _kaydet_ve_ekle(combined, domain, len(visited), skipped)


def _kaydet_ve_ekle(combined_text: str, domain: str, crawled: int, skipped: int) -> dict:
    """Birleştirilmiş metni uploads/'a yazar ve RagManager'a belge olarak ekler (her iki tarayıcı da kullanır)."""
    slug = re.sub(r'[^a-zA-Z0-9]', '_', domain)[:40]
    os.makedirs('uploads', exist_ok=True)
    path = f'uploads/web_{slug}.txt'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(combined_text)
    doc_name = state.rag_manager.add_document(path)
    return {'crawled': crawled, 'skipped': skipped, 'doc_name': doc_name}


def _website_to_rag_firecrawl(start_url, max_pages, status_cb=None):
    """Firecrawl API'siyle taramayı dener. Başarısız olursa çağıran taraf klasik tarayıcıya düşer."""
    from firecrawl import Firecrawl

    def log(m):
        print(f'[CRAWLER] {m}')
        if status_cb: status_cb(m)

    api_key = os.environ.get('FIRECRAWL_API_KEY')
    fc = Firecrawl(api_key=api_key)

    log(f'Firecrawl ile taranıyor: {start_url}')
    job = fc.crawl(url=start_url, limit=max_pages, poll_interval=2, timeout=300)

    sayfalar = getattr(job, 'data', None) or []
    if not sayfalar:
        return {'crawled': 0, 'skipped': 0, 'doc_name': None}

    texts = []
    for sayfa in sayfalar:
        markdown = getattr(sayfa, 'markdown', None)
        if not markdown or len(markdown) < 100:
            continue
        meta = getattr(sayfa, 'metadata', None)
        kaynak_url = getattr(meta, 'source_url', None) or start_url
        texts.append(f"\n\n{'='*60}\nKAYNAK: {kaynak_url}\n{'='*60}\n{markdown}")
        log(f'✅ [{len(texts)}/{len(sayfalar)}] {kaynak_url}')

    if not texts:
        return {'crawled': 0, 'skipped': len(sayfalar), 'doc_name': None}

    domain = urlparse(start_url).netloc
    combined = f"WEB SİTESİ (Firecrawl): {start_url}\nTarih: {time.strftime('%Y-%m-%d %H:%M')}\n" + ''.join(texts)
    return _kaydet_ve_ekle(combined, domain, len(texts), len(sayfalar) - len(texts))


def website_to_rag(start_url, max_pages=30, delay=0.3, respect_robots=True, status_cb=None):
    """
    Web sitesini RAG'a belge olarak ekler. FIRECRAWL_API_KEY tanımlıysa Firecrawl API'sini
    dener (JS render, temiz markdown); key yoksa veya Firecrawl çağrısı başarısız olursa
    mevcut urllib/HTMLParser tabanlı klasik tarayıcıya düşülür.
    """
    ensure_imports()

    if os.environ.get('FIRECRAWL_API_KEY'):
        try:
            return _website_to_rag_firecrawl(start_url, max_pages, status_cb)
        except Exception as e:
            print(f'⚠️ Firecrawl taraması başarısız, klasik tarayıcıya dönülüyor: {e}')

    return _website_to_rag_klasik(start_url, max_pages, delay, respect_robots, status_cb)
