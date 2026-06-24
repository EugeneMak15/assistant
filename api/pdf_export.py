"""
Branded PDF export of a chat's search results — found equipment + consultant notes.

Pure-Python (fpdf2 + Pillow), no system dependencies. Bundles DejaVuSans for full
Unicode (incl. Cyrillic) so recommendations in any language render correctly.
"""
import os, re, io, urllib.request

from fpdf import FPDF

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ASSETS = os.path.join(_HERE, "assets")
_LOGO_SVG = os.path.join(_ASSETS, "bzb-logo.svg")
_FONT_REG = os.path.join(_ASSETS, "fonts", "DejaVuSans.ttf")
_FONT_BLD = os.path.join(_ASSETS, "fonts", "DejaVuSans-Bold.ttf")

_UA = "BZBAdvisor/1.0 (sales@bzbgear.com)"

# Brand palette
_NAVY = (15, 23, 42)
_BLUE = (37, 99, 235)
_GREY = (100, 116, 139)
_LIGHT = (241, 245, 249)
_GREEN = (22, 163, 74)

_CONTACT = {
    "name":    "BZB Gear",
    "address": "830 National Dr Ste 140, Sacramento, CA 95834, USA",
    "office":  "(888) 499-9906",
    "local":   "+1 (916) 383-3154",
    "email":   "sales@bzbgear.com",
    "web":     "bzbgear.com",
}

MARGIN = 15
_IMG_CACHE: dict = {}


_OG_CACHE: dict = {}


def _main_image_url(product: dict) -> str:
    """Return the product's MAIN image — the page's og:image — falling back to the
    stored image_url (which can be a gallery/content shot, not the hero)."""
    purl = str(product.get("product_url") or "")
    if purl:
        if purl in _OG_CACHE:
            og = _OG_CACHE[purl]
            if og:
                return og
        else:
            og = None
            try:
                req = urllib.request.Request(purl, headers={"User-Agent": _UA})
                html = urllib.request.urlopen(req, timeout=6).read().decode("utf-8", "replace")
                m = (re.search(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)', html) or
                     re.search(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image', html))
                if m:
                    og = m.group(1)
            except Exception:
                og = None
            _OG_CACHE[purl] = og
            if og:
                return og
    return str(product.get("image_url") or "")


def _fetch_image(url: str):
    """Download a product image and return (BytesIO PNG, w_px, h_px) or None.
    Transparent areas are flattened onto WHITE (not black/green)."""
    if not url:
        return None
    if url in _IMG_CACHE:
        return _IMG_CACHE[url]
    result = None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        data = urllib.request.urlopen(req, timeout=6).read()
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.alpha_composite(img)
        img = bg.convert("RGB")
        out = io.BytesIO()
        img.save(out, format="PNG")
        out.seek(0)
        result = (out, img.width, img.height)
    except Exception:
        result = None
    _IMG_CACHE[url] = result
    return result


class _PDF(FPDF):
    def header(self):
        try:
            self.image(_LOGO_SVG, x=MARGIN, y=11, w=50)
        except Exception:
            self.set_xy(MARGIN, 13)
            self.set_font("DejaVu", "B", 18); self.set_text_color(*_NAVY)
            self.cell(0, 8, "BZBGEAR")
        self.set_xy(0, 14)
        self.set_font("DejaVu", "B", 15); self.set_text_color(*_NAVY)
        self.cell(self.w - MARGIN, 7, "AV Equipment Recommendation", align="R")
        self.set_xy(0, 22)
        self.set_font("DejaVu", "", 9); self.set_text_color(*_GREY)
        self.cell(self.w - MARGIN, 5, "Amplify Your World™", align="R")
        self.set_draw_color(*_BLUE); self.set_line_width(0.6)
        self.line(MARGIN, 31, self.w - MARGIN, 31)
        self.set_y(37)

    def footer(self):
        self.set_y(-12)
        self.set_font("DejaVu", "", 7.5); self.set_text_color(*_GREY)
        self.cell(0, 5, f"{_CONTACT['web']}   ·   Page {self.page_no()}", align="C")


def _fmt_price(v):
    try:
        return f"${float(v):,.0f}"
    except Exception:
        return ""


def _content_w(pdf) -> float:
    return pdf.w - 2 * MARGIN


def _best_pick_sku(rec_text: str) -> str:
    """Extract the recommended SKU from the 'Best pick for your case:' line."""
    if not rec_text:
        return ""
    m = re.search(r'Best pick for your case:\s*\**\s*((?:BG|BZ)-[A-Z0-9\-]+)',
                  rec_text, re.I)
    return m.group(1).upper() if m else ""


def _is_best(sku: str, best: str) -> bool:
    """Match tolerant of color/variant suffixes (BG-X vs BG-X-B)."""
    if not best:
        return False
    s, b = sku.upper(), best.upper()
    return s == b or s.startswith(b + "-") or b.startswith(s + "-")


def _product_card(pdf, p: dict, is_best: bool = False):
    """Render one product: thumbnail + SKU/name/stock + price, in a clean row."""
    sku   = str(p.get("id", ""))
    name  = str(p.get("name") or "").strip()
    title = str(p.get("title") or "").strip()
    # Some products (e.g. BG-MC series) store the SKU in `name` and the real
    # description in `title` — prefer the descriptive one.
    if not name or name.upper() == sku.upper():
        name = title or sku
    price = _fmt_price(p.get("price_usd"))
    stock = str(p.get("stock_status") or "")
    url   = str(p.get("product_url") or "")
    img   = _fetch_image(_main_image_url(p))

    # Page-break guard — keep a card from splitting awkwardly
    if pdf.get_y() > pdf.h - (52 if is_best else 45):
        pdf.add_page()

    box_top = pdf.get_y()
    if is_best:
        # Green "best pick" badge above the card
        pdf.set_xy(MARGIN + 3, box_top + 2)
        pdf.set_font("DejaVu", "B", 8.5); pdf.set_text_color(*_GREEN)
        pdf.cell(0, 5, "★ BEST PICK FOR YOUR CASE", new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(MARGIN + 3)
        pdf.ln(0.5)

    y0 = pdf.get_y()
    sku_x_pad = 3 if is_best else 0
    left = MARGIN + sku_x_pad          # inset content when best (room for border)
    right_pad = sku_x_pad
    img_w = img_h = 0
    if img:
        io_png, wpx, hpx = img
        img_w = 24
        img_h = img_w * hpx / wpx
        if img_h > 20:
            img_h = 20
            img_w = img_h * wpx / hpx
        try:
            pdf.image(io_png, x=left, y=y0, w=img_w, h=img_h)
        except Exception:
            img_w = img_h = 0

    tx = left + (img_w + 4 if img_w else 0)
    tw = pdf.w - MARGIN - right_pad - tx     # width available for text
    price_w = 30

    # SKU (bold — green if best pick, else blue) + price (bold green, right)
    pdf.set_xy(tx, y0)
    pdf.set_font("DejaVu", "B", 11)
    pdf.set_text_color(*(_GREEN if is_best else _BLUE))
    pdf.cell(tw - price_w, 6, sku)
    if price:
        pdf.set_xy(pdf.w - MARGIN - right_pad - price_w, y0)
        pdf.set_font("DejaVu", "B", 11); pdf.set_text_color(*_GREEN)
        pdf.cell(price_w, 6, price, align="R")
    # Name (wrapped)
    pdf.set_xy(tx, y0 + 6.5)
    pdf.set_font("DejaVu", "", 9); pdf.set_text_color(*_NAVY)
    pdf.multi_cell(tw, 4.6, name)
    # Stock + link
    pdf.set_x(tx)
    pdf.set_font("DejaVu", "", 8); pdf.set_text_color(*_GREY)
    meta = stock
    if url:
        pdf.cell(tw, 4.5, (stock + "   " if stock else "") + "View product →", link=url)
        pdf.ln(4.5)
    elif meta:
        pdf.multi_cell(tw, 4.5, meta)

    text_bottom = pdf.get_y()
    row_bottom = max(text_bottom, y0 + img_h)
    # Green border around the recommended card (draw-only, doesn't cover content)
    if is_best:
        pdf.set_draw_color(*_GREEN); pdf.set_line_width(0.5)
        pdf.rect(MARGIN, box_top, _content_w(pdf), row_bottom - box_top + 3)
    pdf.set_y(row_bottom + (6 if is_best else 5))


def _format_note_line(line: str) -> str:
    """Bold leading SKU and section labels for markdown rendering."""
    s = line.rstrip()
    if not s.strip():
        return ""
    # Bold section labels at the start of a line
    s = re.sub(
        r'^(\s*)(Best pick for your case:|Best for:|Pros:|Cons:|Limitations:|Notes?:)',
        lambda m: f"{m.group(1)}**{m.group(2)}**", s,
    )
    # Bold a leading SKU when it isn't already bold
    if not s.lstrip().startswith("**"):
        s = re.sub(r'^(\s*)((?:BG|BZ)-[A-Z0-9\-]+)',
                   lambda m: f"{m.group(1)}**{m.group(2)}**", s)
    return s


def _clean_notes(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.M)   # drop md headings
    text = text.replace("---", "")
    return text.strip()


def generate_recommendation_pdf(products: list[dict], rec_text: str, topic: str = "") -> bytes:
    pdf = _PDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_font("DejaVu", "", _FONT_REG)
    pdf.add_font("DejaVu", "B", _FONT_BLD)
    pdf.set_margins(MARGIN, 12, MARGIN)
    pdf.add_page()

    if topic:
        pdf.set_font("DejaVu", "", 10); pdf.set_text_color(*_GREY)
        pdf.multi_cell(_content_w(pdf), 5, f"Prepared for your request: {topic}")
        pdf.ln(2)

    # ── Equipment ──────────────────────────────────────────────────────
    best = _best_pick_sku(rec_text)
    # Put the recommended product first so it leads the list
    ordered = sorted(products, key=lambda p: 0 if _is_best(str(p.get("id", "")), best) else 1)
    pdf.set_font("DejaVu", "B", 12); pdf.set_text_color(*_NAVY)
    pdf.cell(0, 8, "Recommended Equipment", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    for p in ordered:
        _product_card(pdf, p, is_best=_is_best(str(p.get("id", "")), best))

    # ── Consultant notes ───────────────────────────────────────────────
    notes = _clean_notes(rec_text)
    if notes:
        pdf.ln(3)
        pdf.set_font("DejaVu", "B", 12); pdf.set_text_color(*_NAVY)
        pdf.cell(0, 8, "Consultant Notes & Comparison", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_text_color(40, 40, 40)
        for raw in notes.split("\n"):
            line = _format_note_line(raw)
            if not line:
                pdf.ln(2.5)
                continue
            pdf.set_x(MARGIN)
            pdf.set_font("DejaVu", "", 9.5)
            pdf.multi_cell(_content_w(pdf), 5.2, line, markdown=True,
                           new_x="LMARGIN", new_y="NEXT")

    # ── Contact block (prominent, end of doc) ──────────────────────────
    if pdf.get_y() > pdf.h - 60:
        pdf.add_page()
    pdf.ln(8)
    y = pdf.get_y()
    pdf.set_fill_color(*_LIGHT)
    pdf.rect(MARGIN, y, _content_w(pdf), 38, style="F")
    pdf.set_xy(MARGIN + 6, y + 5)
    pdf.set_font("DejaVu", "B", 14); pdf.set_text_color(*_BLUE)
    pdf.cell(0, 7, "Contact BZB Gear", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(MARGIN + 6)
    pdf.set_font("DejaVu", "", 10.5); pdf.set_text_color(*_NAVY)
    for label, val in [
        ("Address", _CONTACT["address"]),
        ("Office",  _CONTACT["office"]),
        ("Local",   _CONTACT["local"]),
        ("Email",   _CONTACT["email"]),
    ]:
        pdf.set_x(MARGIN + 6)
        pdf.set_font("DejaVu", "B", 10.5)
        pdf.cell(20, 5.6, label)
        pdf.set_font("DejaVu", "", 10.5)
        pdf.cell(0, 5.6, val, new_x="LMARGIN", new_y="NEXT")

    out = pdf.output()
    return bytes(out)
