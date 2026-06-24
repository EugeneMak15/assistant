"""Layer 1 — SQL coarse filter. Eliminates 95% of products by structured specs."""
from .db import get_conn, row_to_dict
from .models import SessionState, Product


RESOLUTION_ORDER = ["720p", "1080p", "1080p60", "4K30", "4K60", "4K120", "8K30", "8K60"]

def resolution_rank(res: str) -> int:
    try:
        return RESOLUTION_ORDER.index(res)
    except ValueError:
        return -1

def normalize_resolution(res: str) -> str:
    """Map user-facing resolution strings to DB values."""
    mapping = {
        "1080p": "1080p", "1080": "1080p", "fhd": "1080p",
        "4k30": "4K30", "4k": "4K30",
        "4k60": "4K60", "4k@60": "4K60", "4k 60": "4K60",
        "4k120": "4K120",
        "8k": "8K30", "8k30": "8K30", "8k60": "8K60",
    }
    return mapping.get(res.lower().replace(" ", ""), res)


def get_candidates(session: SessionState, category: str | None = None) -> list[Product]:
    """
    Layer 1: SQL coarse filter.
    Returns products matching the session constraints.
    At most 8 candidates returned to keep context small.
    """
    conn = get_conn()
    conditions = []
    params: list = []

    # Category filter (from session venue_type heuristics or explicit)
    if category:
        conditions.append("category = ?")
        params.append(category)

    # Inputs / outputs
    if session.num_inputs is not None:
        conditions.append("(inputs IS NULL OR inputs >= ?)")
        params.append(session.num_inputs)

    if session.num_outputs is not None:
        conditions.append("(outputs IS NULL OR outputs >= ?)")
        params.append(session.num_outputs)

    # Distance — only for extenders/splitters
    if session.max_distance_m and session.max_distance_m > 10:
        conditions.append("(max_distance_m IS NULL OR max_distance_m >= ?)")
        params.append(session.max_distance_m)

    # Resolution — check if resolution column contains the required resolution
    if session.resolution:
        norm = normalize_resolution(session.resolution)
        # SQLite: resolutions is a JSON array string, do a simple LIKE check
        conditions.append("(resolutions LIKE ? OR resolutions IS NULL)")
        params.append(f'%"{norm}"%')

    conditions.append("(site_category IS NULL OR site_category != 'Discontinued')")
    where = " AND ".join(conditions)
    sql = f"SELECT * FROM products WHERE {where} ORDER BY id LIMIT 8"

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    return [Product(**row_to_dict(r)) for r in rows]


def get_product(product_id: str) -> Product | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    conn.close()
    return Product(**row_to_dict(row)) if row else None


def search_products(
    category: str | None = None,
    min_inputs: int | None = None,
    min_outputs: int | None = None,
    resolution: str | None = None,
    min_distance_m: int | None = None,
    signal_type: str | None = None,
    limit: int = 8,
) -> list[Product]:
    """Flexible product search — used by /candidates endpoint."""
    conn = get_conn()
    conditions = []
    params: list = []

    if category:
        conditions.append("category = ?")
        params.append(category)
    if min_inputs is not None:
        conditions.append("(inputs IS NULL OR inputs >= ?)")
        params.append(min_inputs)
    if min_outputs is not None:
        conditions.append("(outputs IS NULL OR outputs >= ?)")
        params.append(min_outputs)
    if min_distance_m is not None:
        conditions.append("(max_distance_m IS NULL OR max_distance_m >= ?)")
        params.append(min_distance_m)
    if resolution:
        norm = normalize_resolution(resolution)
        conditions.append('(resolutions LIKE ? OR resolutions IS NULL OR resolutions = "[]")')
        params.append(f'%"{norm}"%')
    if signal_type:
        # Filter by signal type in input_signals OR output_signals JSON arrays
        sig = signal_type.upper()
        conditions.append(
            "(input_signals LIKE ? OR output_signals LIKE ? "
            "OR input_signals IS NULL OR input_signals = '[]')"
        )
        params.extend([f'%{sig}%', f'%{sig}%'])

    conditions.append("(site_category IS NULL OR site_category != 'Discontinued')")
    where = " AND ".join(conditions)
    sql = f"SELECT * FROM products WHERE {where} ORDER BY id LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [Product(**row_to_dict(r)) for r in rows]
