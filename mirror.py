#!/usr/bin/env python3
"""Mirror https://www.maison-lavande-provence.fr into a static site in docs/."""
import os
import re
import sys
import time
import posixpath
from collections import deque
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urldefrag, unquote
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BASE_HOST = "www.maison-lavande-provence.fr"
BASE = f"https://{BASE_HOST}"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

SEEDS = [
    "/",
    "/a-propos/",
    "/contact/",
    "/livret/",
    "/le-sur-mesure/",
    "/nos-creations/",
    "/nos-valeurs/",
    "/politique-de-confidentialite-rgpd/",
    "/conditions-generales-dutilisation-cgu/",
    "/conditions-generales-de-vente-cgv/",
    "/privacy-policy/",
    "/shop/",
    "/cart/",
    "/checkout/",
    "/my-account/",
]

# URL prefixes that are dead in a static world — never fetch them.
SKIP_PREFIXES = (
    "/wp-admin/", "/wp-login", "/xmlrpc.php", "/wp-json/",
    "/feed/", "/?s=", "/wp-cron",
)

FETCHED = {}          # normalized url -> local path (relative to OUT)
QUEUE = deque()       # urls to fetch
IS_PAGE = {}          # normalized url -> bool

CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^)'\"]+)\1\s*\)")
SRCSET_SPLIT = re.compile(r"\s*,\s*")


def norm(url):
    """Normalize a url: absolute, defrag'd, same-host only or None."""
    url = url.strip()
    if not url or url.startswith(("#", "mailto:", "tel:", "javascript:", "data:", "sms:", "skype:")):
        return None
    url = urljoin(BASE + "/", url)
    url, _frag = urldefrag(url)
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return None
    if p.netloc != BASE_HOST:
        return None
    return url


def is_probably_page(url):
    path = urlparse(url).path
    if path == "" or path.endswith("/"):
        return True
    ext = os.path.splitext(path)[1].lower()
    return ext in ("", ".html", ".htm", ".php")


def local_path(url):
    """Local output path (relative) for a same-host url."""
    p = urlparse(url)
    path = unquote(p.path)
    if path in ("", "/") or path.endswith("/"):
        path = path + "index.html" if path.endswith("/") else "/index.html"
    elif is_probably_page(url):
        path = path.rstrip("/") + "/index.html"
    # strip query only via caller-normalized url (we keep full url w/ query out of path)
    return path.lstrip("/")


def enqueue(url, page=False):
    n = norm(url)
    if n is None:
        return
    if any(urlparse(n).path.startswith(s) or urlparse(n).path == s.rstrip("/")
           for s in SKIP_PREFIXES):
        return
    if n in FETCHED:
        IS_PAGE[n] = IS_PAGE.get(n, False) or page
        return
    FETCHED[n] = local_path(n)
    IS_PAGE[n] = page
    QUEUE.append(n)


def fetch(url):
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urlopen(req, timeout=30) as r:
        ctype = r.headers.get("Content-Type", "")
        return r.read(), ctype


class RefParser(HTMLParser):
    """Collect asset refs and page links from HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs = []
        self.links = []
        self._in_style = False

    def _add_attrs(self, attrs):
        d = dict(attrs)
        for a in ("src", "href", "poster", "data-src", "data-bg", "data-href"):
            if d.get(a):
                self.refs.append(d[a])
        for a in ("srcset", "data-srcset"):
            if d.get(a):
                for cand in SRCSET_SPLIT.split(d[a]):
                    u = cand.strip().split(" ")[0]
                    if u:
                        self.refs.append(u)
        if d.get("style"):
            for m in CSS_URL_RE.finditer(d["style"]):
                self.refs.append(m.group(2))

    def handle_starttag(self, tag, attrs):
        if tag == "style":
            self._in_style = True
        d = dict(attrs)
        if tag == "a" and d.get("href"):
            self.links.append(d["href"])
            return
        if tag == "link" and d.get("rel") and "canonical" in d.get("rel", ""):
            return  # keep canonical absolute, don't fetch
        if tag == "meta":
            return  # og:image etc — keep absolute, don't fetch
        self._add_attrs(attrs)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "style":
            self._in_style = False

    def handle_data(self, data):
        if self._in_style:
            for m in CSS_URL_RE.finditer(data):
                self.refs.append(m.group(2))


def rel_url(from_local, to_url):
    """Relative url from a page's local path to a same-site (root-relative) url."""
    p = urlparse(to_url)
    target = unquote(p.path)
    frag = ("#" + p.fragment) if p.fragment else ""
    q = ("?" + p.query) if p.query else ""
    page_dir = posixpath.dirname(from_local)
    if target == "" or target.endswith("/"):
        tdir = target.lstrip("/") or "."
        rel = posixpath.relpath(tdir, page_dir or ".")
        if rel == ".":
            rel = ""
        elif not rel.endswith("/"):
            rel += "/"
        return rel + q + frag
    rel = posixpath.relpath(target.lstrip("/"), page_dir or ".")
    return rel + q + frag


ATTR_RE = re.compile(
    r'(\b(?:href|src|action|poster|data-src|data-bg|data-href|data-oembed_url|content)\s*=\s*)(["\'])(/[^"\']*|https?://(?:www\.)?maison-lavande-provence\.fr[^"\']*)\2',
    re.IGNORECASE,
)
SRCSET_ATTR_RE = re.compile(r'(\bsrcset\s*=\s*)(["\'])(.*?)\2', re.DOTALL | re.IGNORECASE)
STYLE_TAG_RE = re.compile(r"(<style[^>]*>)(.*?)(</style>)", re.DOTALL | re.IGNORECASE)
STYLE_ATTR_RE = re.compile(r'(\bstyle\s*=\s*)(["\'])(.*?)\2', re.DOTALL | re.IGNORECASE)
META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
CANONICAL_RE = re.compile(r'<link\b[^>]*rel=["\']?canonical["\']?[^>]*>', re.IGNORECASE)

STRIP_RES = [
    re.compile(r'<link\b[^>]*rel=["\']https://api\.w\.org/["\'][^>]*>', re.IGNORECASE),
    re.compile(r'<link\b[^>]*rel=["\']?shortlink["\']?[^>]*>', re.IGNORECASE),
    re.compile(r'<link\b[^>]*rel=["\']?alternate["\']?[^>]*(?:rss|atom|wp-json|oembed)[^>]*>', re.IGNORECASE),
    re.compile(r'<meta\b[^>]*name=["\']generator["\'][^>]*>', re.IGNORECASE),
]

ABS_BASE_RE = re.compile(r'https?://(?:www\.)?maison-lavande-provence\.fr')
ABS_BASE_ESC_RE = re.compile(r'https?:\\?/\\?/(?:www\.)?maison-lavande-provence\.fr')
PROTO_REL_RE = re.compile(r'(?<![:"\'/\w])//(?:www\.)?maison-lavande-provence\.fr')


def rewrite_css(css_text, css_local):
    """Download + rewrite url() refs inside a css file."""
    def repl(m):
        u = m.group(2).strip()
        if not u or u.startswith(("data:", "#")):
            return m.group(0)
        abs_u = urljoin(BASE + "/" + css_local, u)
        n = norm(abs_u)
        if n is None:
            return m.group(0)
        enqueue(n)
        css_dir = posixpath.dirname(css_local)
        rel = posixpath.relpath(FETCHED[n], css_dir or ".")
        p = urlparse(n)
        suffix = (("#" + p.fragment) if p.fragment else "")
        return f"url({rel}{suffix})"
    return CSS_URL_RE.sub(repl, css_text)


def rewrite_srcset(value, from_local):
    out = []
    for cand in SRCSET_SPLIT.split(value):
        cand = cand.strip()
        if not cand:
            continue
        parts = cand.split(" ")
        u = parts[0]
        if u.startswith("/") and not u.startswith("//"):
            # resolve to find local path
            fake = BASE + u
            n = norm(fake)
            if n and n in FETCHED:
                parts[0] = rel_url(from_local, u)
        elif ABS_BASE_RE.match(u):
            n = norm(u)
            if n and n in FETCHED:
                parts[0] = rel_url(from_local, urlparse(n).path + (("?" + n.split("?", 1)[1]) if "?" in n else ""))
        out.append(" ".join(parts))
    return ", ".join(out)


def rewrite_html(html, local):
    # 1) protect <meta> tags and canonical link (keep absolute URLs there)
    protected = []

    def stash(m):
        protected.append(m.group(0))
        return f"\x00{len(protected) - 1}\x00"

    html = META_TAG_RE.sub(stash, html)
    html = CANONICAL_RE.sub(stash, html)

    # 2) strip dead WP tags
    for r in STRIP_RES:
        html = r.sub("", html)

    # 3) absolute same-site urls -> root-relative (incl. escaped JSON form)
    html = ABS_BASE_ESC_RE.sub("", html)
    html = ABS_BASE_RE.sub("", html)
    html = PROTO_REL_RE.sub("", html)

    # 4) dead endpoints -> '#'
    html = re.sub(r'(?<=[\'"(=])/wp-admin/admin-ajax\.php[^\'")]*', "#", html)
    html = re.sub(r'(?<=[\'"(=])/wp-json/[^\'")]*', "#", html)

    # 5) rewrite root-relative refs in attributes -> relative
    def attr_repl(m):
        prefix, q, u = m.group(1), m.group(2), m.group(3)
        if u.startswith(("//", "/wp-admin/", "/wp-login", "/xmlrpc.php", "/wp-json/")):
            return m.group(0)
        n = norm(BASE + u)
        if n is not None and n in FETCHED and not IS_PAGE.get(n):
            return f"{prefix}{q}{rel_url(local, u)}{q}"
        if n is not None:
            return f"{prefix}{q}{rel_url(local, u)}{q}"
        return m.group(0)

    html = ATTR_RE.sub(attr_repl, html)

    # 6) srcset
    html = SRCSET_ATTR_RE.sub(
        lambda m: m.group(1) + m.group(2) + rewrite_srcset(m.group(3), local) + m.group(2),
        html,
    )

    # 7) url() inside style tags and style attributes
    def css_repl(css):
        def r(m):
            u = m.group(2).strip()
            if not u or u.startswith(("data:", "#", "http", "//")):
                if u.startswith("/"):
                    pass
                else:
                    return m.group(0)
            if u.startswith("/") and not u.startswith("//"):
                return f"url({rel_url(local, u)})"
            return m.group(0)
        return CSS_URL_RE.sub(r, css)

    html = STYLE_TAG_RE.sub(lambda m: m.group(1) + css_repl(m.group(2)) + m.group(3), html)
    html = STYLE_ATTR_RE.sub(
        lambda m: m.group(1) + m.group(2) + css_repl(m.group(3)) + m.group(2), html
    )

    # 8) restore protected tags
    def unstash(m):
        return protected[int(m.group(1))]

    html = re.sub("\x00(\\d+)\x00", unstash, html)
    return html


def main():
    os.makedirs(OUT, exist_ok=True)
    for s in SEEDS:
        enqueue(s, page=True)

    while QUEUE:
        url = QUEUE.popleft()
        local = FETCHED[url]
        dest = os.path.join(OUT, local)
        if os.path.exists(dest):
            continue
        try:
            data, ctype = fetch(url)
        except Exception as e:
            print(f"FAIL {url}: {e}", file=sys.stderr)
            del FETCHED[url]
            continue
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)

        if "text/css" in ctype or local.endswith(".css"):
            data = rewrite_css(data.decode("utf-8", errors="replace"), local).encode("utf-8")
        elif ("text/html" in ctype or IS_PAGE.get(url)) and b"<" in data[:500]:
            text = data.decode("utf-8", errors="replace")
            parser = RefParser()
            try:
                parser.feed(text)
            except Exception:
                pass
            for u in parser.refs:
                enqueue(u)
            for u in parser.links:
                enqueue(u, page=True)
            data = rewrite_html(text, local).encode("utf-8")

        with open(dest, "wb") as f:
            f.write(data)
        print(f"OK {url} -> {local} ({len(data)} o)")
        time.sleep(0.05)

    print(f"\nDone: {len(FETCHED)} urls")


if __name__ == "__main__":
    main()
