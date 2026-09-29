"""Deterministic customer requirements and catalog eligibility checks."""

import json
import re


MEDICAL_TERMS = re.compile(
    r"\b(medical|medicine|healthcare|hospital|clinic|clinical|patient|surgery|"
    r"telemedicine|telehealth|doctor|медицин\w*|больниц\w*|клиник\w*|пациент\w*|врач\w*)\b",
    re.I,
)


def requirement_text(question: str = "", answers: dict | None = None, plan: dict | None = None) -> str:
    plan = plan or {}
    return " ".join(str(x) for x in (
        question,
        plan.get("search_query", ""),
        plan.get("scenario_summary", ""),
        *(answers or {}).values(),
    ) if x).lower()


def requested_video(text: str) -> tuple[bool, bool]:
    """Return explicit 8K and 4K120 requirements (not generic 4K)."""
    return bool(re.search(r"\b8\s*k\b", text, re.I)), bool(
        re.search(r"\b4\s*k\s*(?:@|/|at)?\s*120\b", text, re.I)
    )


def requested_ports(text: str) -> tuple[int | None, int | None]:
    matrix = re.search(r"\b(\d{1,2})\s*[x×]\s*(\d{1,2})\b", text, re.I)
    if matrix:
        return int(matrix.group(1)), int(matrix.group(2))
    words = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6"}
    for word, number in words.items():
        text = re.sub(rf"\b{word}\s+(?=(?:hdmi\s*)?(?:sources?|inputs?|tvs?|displays?|screens?)\b)", number + " ", text, flags=re.I)
    inputs = re.search(r"\b(\d{1,2})\s*(?:hdmi\s*)?(?:sources?|inputs?|источник\w*)\b", text, re.I)
    outputs = re.search(r"\b(\d{1,2})\s*(?:tvs?|displays?|screens?|outputs?|монитор\w*|экран\w*|телевизор\w*)\b", text, re.I)
    one_display = bool(re.search(r"\b(?:one|single|один|одно|одного)\s+(?:tv|display|screen|телевизор\w*|экран\w*)\b", text, re.I))
    return int(inputs.group(1)) if inputs else None, int(outputs.group(1)) if outputs else (1 if one_display else None)


def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    try:
        result = json.loads(value or "[]")
        return result if isinstance(result, list) else []
    except (TypeError, ValueError):
        return []


def hard_mismatch(product: dict, interface: dict | None, text: str, categories: list[str] | None = None) -> str | None:
    """Return the violated hard requirement, or None if the product can be shown."""
    sku = product.get("id", "").upper()
    interface = interface or {}
    cats = " ".join(categories or []).lower()
    name = (product.get("name") or "").lower()
    if product.get("category") == "accessory" or any(word in name for word in ("wall mount", "ceiling mount", "mounting bracket")):
        return "accessory, not primary equipment"
    if "NUTRIX" in sku and not MEDICAL_TERMS.search(text):
        return "medical-only camera outside a medical scenario"

    need_8k, need_4k120 = requested_video(text)
    need_4k = bool(re.search(r"\b4\s*k\b", text, re.I))
    need_4k60 = bool(re.search(r"\b4\s*k\s*(?:@|/|at)?\s*60\b", text, re.I))
    video_device = not cats or any(term in cats for term in ("switch", "matrix", "camera", "encoder", "decoder", "extender", "av over ip"))
    if video_device and need_8k:
        evidence = name + " " + " ".join(_json_list(product.get("features"))).lower()
        if interface.get("supports_8k") != 1 or "8K" not in evidence.upper():
            return "8K required"
    if video_device and need_4k and interface.get("supports_4k") != 1:
        return "4K required"
    if video_device and need_4k60 and (interface.get("max_res") or "").upper() in {"1080P", "1080P60", "4K30"}:
        return "4K60 required"
    if video_device and need_4k120:
        if (interface.get("max_res") or "").upper() in {"1080P", "1080P60", "4K30", "4K60"}:
            return "4K120 required"
        resolutions = _json_list(product.get("resolutions"))
        features = " ".join(_json_list(product.get("features"))).lower()
        name = (product.get("name") or "").lower()
        if not any(re.search(r"4\s*k\s*(?:@|/|at)?\s*120", s, re.I) for s in resolutions + [features, name]):
            return "4K120 required"

    ndi_device = not cats or any(term in cats for term in ("camera", "encoder", "decoder", "av over ip"))
    if ndi_device and re.search(r"\bndi\b", text) and not re.search(r"\b(?:no|without|non)\s+ndi\b", text):
        if "technology=dante" in (product.get("product_url") or "").lower():
            return "Dante variant does not provide NDI output"
        if interface.get("out_ndi") != 1:
            return "NDI output required"

    if "encoder" in cats and product.get("category") != "encoder_decoder":
        return "dedicated streaming encoder required"

    if "switcher" in cats or "matrix" in cats:
        if product.get("category") not in {"switcher", "presentation_switcher"}:
            return "wrong switcher category"
        inputs, outputs = requested_ports(text)
        if inputs and (interface.get("in_hdmi_count") or 0) < inputs:
            return "insufficient HDMI inputs"
        if outputs and (interface.get("out_hdmi_count") or 0) < outputs:
            return "insufficient HDMI outputs"
        if inputs and (interface.get("in_hdmi_count") or 0) > inputs * 2:
            return "excessive input capacity"
        if outputs and (interface.get("out_hdmi_count") or 0) > outputs * 2:
            return "excessive output capacity"
        if "matrix" in text and (interface.get("out_hdmi_count") or 0) < 2:
            return "independent matrix outputs required"
        if "multiview" not in text and "multiviewer" in name:
            return "multiviewer was not requested"
        if product.get("category") == "presentation_switcher" and "presentation" not in text:
            return "presentation switcher was not requested"
    return None


def rank_product(product: dict, interface: dict | None, text: str) -> tuple:
    """Prefer the closest port count after hard requirements pass."""
    interface = interface or {}
    inputs, outputs = requested_ports(text)
    return (
        max(0, (interface.get("out_hdmi_count") or 0) - outputs) if outputs else 0,
        max(0, (interface.get("in_hdmi_count") or 0) - inputs) if inputs else 0,
        product.get("price_usd") or 0,
    )


def camera_family_key(sku: str) -> str:
    """Keep signal/technology suffixes while collapsing zoom and color variants."""
    sku = re.sub(r"-(B|W|S|G)$", "", sku.upper())
    sku = re.sub(r"\d{1,2}X(?=-|$)", "ZX", sku)
    return re.sub(r"-(10|12|20|25|30)(?=HSU|HSP|X)", "-Z", sku)


def camera_family_variants(conn, sku: str) -> list[dict]:
    key = camera_family_key(sku)
    if key == sku.upper():
        return []
    variants = []
    for row in conn.execute("""SELECT id, product_url, price_usd, stock_status FROM products
                               WHERE category='camera' AND (site_category IS NULL OR site_category != 'Discontinued')
                               AND (stock_status IS NULL OR stock_status NOT IN ('Discontinued', 'Limited Stock'))"""):
        if camera_family_key(row["id"]) == key:
            variants.append(dict(row))
    return sorted(variants, key=lambda item: item["id"])
