"""
Product interfaces schema — structured signal/port/control data extracted from manuals + specs.

Two layers:
  - Flat boolean/integer columns for fast SQL filtering (no JSON parsing at query time)
  - JSON detail columns for LLM context (read only for the selected candidates)
"""
from .db import get_conn


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS product_interfaces (
    sku TEXT PRIMARY KEY,

    -- ── Signal outputs (flat booleans for fast SQL filter) ──────────────────
    out_hdmi        INTEGER DEFAULT 0,   -- any HDMI output
    out_hdmi_count  INTEGER DEFAULT 0,
    out_hdmi_ver    TEXT,                -- '1.4', '2.0', '2.1'
    out_sdi         INTEGER DEFAULT 0,
    out_sdi_count   INTEGER DEFAULT 0,
    out_sdi_ver     TEXT,                -- '3G', '6G', '12G'
    out_ndi         INTEGER DEFAULT 0,   -- NDI / NDI|HX / NDI|HX3
    out_usb_video   INTEGER DEFAULT 0,   -- USB carries video (UVC)
    out_dante       INTEGER DEFAULT 0,   -- Dante AV
    out_hdbaset     INTEGER DEFAULT 0,
    out_fiber       INTEGER DEFAULT 0,
    out_vga         INTEGER DEFAULT 0,
    out_displayport INTEGER DEFAULT 0,
    out_ip_stream   INTEGER DEFAULT 0,   -- RTSP/RTMP/SRT generic IP stream

    -- ── Signal inputs ───────────────────────────────────────────────────────
    in_hdmi         INTEGER DEFAULT 0,
    in_hdmi_count   INTEGER DEFAULT 0,
    in_hdmi_ver     TEXT,
    in_sdi          INTEGER DEFAULT 0,
    in_sdi_count    INTEGER DEFAULT 0,
    in_ndi          INTEGER DEFAULT 0,
    in_usb_video    INTEGER DEFAULT 0,
    in_dante        INTEGER DEFAULT 0,
    in_hdbaset      INTEGER DEFAULT 0,
    in_fiber        INTEGER DEFAULT 0,
    in_vga          INTEGER DEFAULT 0,
    in_displayport  INTEGER DEFAULT 0,
    in_ip_stream    INTEGER DEFAULT 0,

    -- ── Resolution ──────────────────────────────────────────────────────────
    max_res         TEXT,                -- '1080p60','4K30','4K60','8K30','8K60'
    supports_4k     INTEGER DEFAULT 0,
    supports_8k     INTEGER DEFAULT 0,
    supports_hdr    INTEGER DEFAULT 0,

    -- ── Audio ───────────────────────────────────────────────────────────────
    audio_embed_in  INTEGER DEFAULT 0,   -- accepts embedded audio
    audio_embed_out INTEGER DEFAULT 0,   -- passes embedded audio
    audio_analog_in INTEGER DEFAULT 0,   -- analog audio inputs (XLR/RCA/3.5mm)
    audio_deembed   INTEGER DEFAULT 0,   -- can de-embed audio from video

    -- ── Control interfaces ──────────────────────────────────────────────────
    ctrl_ip         INTEGER DEFAULT 0,   -- IP / Telnet / web-UI / REST
    ctrl_rs232      INTEGER DEFAULT 0,
    ctrl_rs422      INTEGER DEFAULT 0,
    ctrl_ir         INTEGER DEFAULT 0,
    ctrl_visca      INTEGER DEFAULT 0,
    ctrl_pelco      INTEGER DEFAULT 0,
    ctrl_front      INTEGER DEFAULT 0,   -- front-panel buttons
    ctrl_api        INTEGER DEFAULT 0,   -- public SDK / API

    -- ── Power ───────────────────────────────────────────────────────────────
    poe             INTEGER DEFAULT 0,   -- accepts PoE
    poe_out         INTEGER DEFAULT 0,   -- provides PoE to downstream

    -- ── Camera-specific ─────────────────────────────────────────────────────
    zoom_optical    INTEGER DEFAULT 0,   -- optical zoom level (12, 20, 25, 30, 31)
    has_tally       INTEGER DEFAULT 0,
    has_autotrack   INTEGER DEFAULT 0,
    has_recording   INTEGER DEFAULT 0,   -- onboard SD/SSD recording

    -- ── Form factor ─────────────────────────────────────────────────────────
    form_factor     TEXT,                -- 'rack-1u','rack-2u','desktop','camera-ptz',
                                         --  'camera-box','camera-usb','inline','kit'

    -- ── Primary function tag ────────────────────────────────────────────────
    primary_fn      TEXT,                -- 'matrix-switcher','encoder','decoder',
                                         --  'extender-tx','extender-rx','camera-ptz',
                                         --  'production-switcher','controller','splitter',
                                         --  'converter','multiviewer','amplifier'

    secondary_fns   TEXT,                -- JSON array of secondary functions
    use_case_tags   TEXT,                -- JSON array: ['sports-bar','broadcast',...]

    -- ── Detail JSON for LLM (loaded only for selected candidates) ───────────
    ports_json      TEXT,                -- USB/Ethernet/audio ports with capabilities
    inputs_json     TEXT,                -- detailed per-port input specs
    outputs_json    TEXT,                -- detailed per-port output specs
    notes           TEXT,                -- LLM extraction notes / caveats

    -- ── Metadata ────────────────────────────────────────────────────────────
    extracted_at    TEXT,
    confidence      REAL DEFAULT 1.0     -- 0–1, extraction confidence
);

CREATE INDEX IF NOT EXISTS idx_pi_out_hdmi   ON product_interfaces(out_hdmi);
CREATE INDEX IF NOT EXISTS idx_pi_out_sdi    ON product_interfaces(out_sdi);
CREATE INDEX IF NOT EXISTS idx_pi_out_ndi    ON product_interfaces(out_ndi);
CREATE INDEX IF NOT EXISTS idx_pi_max_res    ON product_interfaces(max_res);
CREATE INDEX IF NOT EXISTS idx_pi_primary_fn ON product_interfaces(primary_fn);
CREATE INDEX IF NOT EXISTS idx_pi_zoom       ON product_interfaces(zoom_optical);
"""


def init_interfaces_table() -> None:
    conn = get_conn()
    conn.executescript(CREATE_SQL)
    conn.close()


def get_interface(sku: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM product_interfaces WHERE sku=?", (sku,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_interface(data: dict) -> None:
    conn = get_conn()
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" * len(data))
    updates = ", ".join(f"{k}=excluded.{k}" for k in data if k != "sku")
    conn.execute(
        f"INSERT INTO product_interfaces ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT(sku) DO UPDATE SET {updates}",
        list(data.values()),
    )
    conn.commit()
    conn.close()


def filter_by_interfaces(
    primary_fn: str | None = None,
    out_hdmi: bool | None = None,
    out_sdi: bool | None = None,
    out_ndi: bool | None = None,
    out_usb_video: bool | None = None,
    in_hdmi_min: int | None = None,
    in_sdi: bool | None = None,
    supports_4k: bool | None = None,
    supports_8k: bool | None = None,
    zoom_min: int | None = None,
    poe: bool | None = None,
    ctrl_ip: bool | None = None,
    ctrl_rs232: bool | None = None,
    max_res: str | None = None,
) -> list[str]:
    """
    SQL filter on product_interfaces. Returns list of SKUs.
    Only non-None params are applied.
    """
    conditions = []
    params: list = []

    if primary_fn:
        conditions.append("primary_fn = ?")
        params.append(primary_fn)
    if out_hdmi is True:
        conditions.append("out_hdmi = 1")
    if out_sdi is True:
        conditions.append("out_sdi = 1")
    if out_ndi is True:
        conditions.append("out_ndi = 1")
    if out_usb_video is True:
        conditions.append("out_usb_video = 1")
    if in_hdmi_min:
        conditions.append("in_hdmi_count >= ?")
        params.append(in_hdmi_min)
    if in_sdi is True:
        conditions.append("in_sdi = 1")
    if supports_4k is True:
        conditions.append("supports_4k = 1")
    if supports_8k is True:
        conditions.append("supports_8k = 1")
    if zoom_min:
        conditions.append("zoom_optical >= ?")
        params.append(zoom_min)
    if poe is True:
        conditions.append("poe = 1")
    if ctrl_ip is True:
        conditions.append("ctrl_ip = 1")
    if ctrl_rs232 is True:
        conditions.append("ctrl_rs232 = 1")
    if max_res:
        # Map resolution to hierarchy: 1080p < 4K30 < 4K60 < 8K30 < 8K60
        RES_ORDER = ["1080p60", "4K30", "4K60", "8K30", "8K60"]
        try:
            min_idx = RES_ORDER.index(max_res)
            acceptable = RES_ORDER[min_idx:]
            placeholders = ",".join("?" * len(acceptable))
            conditions.append(f"max_res IN ({placeholders})")
            params.extend(acceptable)
        except ValueError:
            pass

    where = " AND ".join(conditions) if conditions else "1"
    conn = get_conn()
    rows = conn.execute(
        f"SELECT sku FROM product_interfaces WHERE {where}", params
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]
