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
    return bool(re.search(r"\b8\s*k(?:\b|(?=\d))", text, re.I)), bool(
        re.search(r"\b4\s*k\s*(?:@|/|at)?\s*120\b", text, re.I)
    )


def is_selected_source_distribution(text: str) -> bool:
    """A selected source mirrored to displays is a splitter, not a matrix."""
    if not re.search(r"\b(?:sources?|inputs?)\b", text, re.I) or not re.search(
        r"\b(?:displays?|screens?|tvs?|outputs?)\b", text, re.I
    ):
        return False
    if re.search(r"\b(?:independent(?:ly)?|different sources? (?:to|on|for) (?:each|different))\b", text, re.I):
        return False
    return bool(re.search(
        r"\b(?:one of (?:them|the (?:\w+\s+){0,2}sources?)|"
        r"either (?:source|input)|one selected (?:source|input)|"
        r"select (?:one|either) (?:source|input))\b",
        text, re.I,
    ))


def requested_ports(text: str) -> tuple[int | None, int | None]:
    matrix = re.search(r"\b(\d{1,2})\s*[x×]\s*(\d{1,2})\b", text, re.I)
    if matrix:
        return int(matrix.group(1)), int(matrix.group(2))
    words = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "eight": "8"}
    for word, number in words.items():
        text = re.sub(rf"\b{word}\s+(?=(?:\d+\s*k\s*)?(?:hdmi\s*)?(?:sources?|inputs?|tvs?|displays?|screens?)\b)", number + " ", text, flags=re.I)
    inputs = re.search(r"\b(\d{1,2})\s*(?:\d+\s*k\s*)?(?:hdmi\s*)?(?:sources?|inputs?|источник\w*)\b", text, re.I)
    outputs = re.search(r"\b(\d{1,2})\s*(?:tvs?|displays?|screens?|outputs?|монитор\w*|экран\w*|телевизор\w*)\b", text, re.I)
    one_display = bool(re.search(r"\b(?:one|single|один|одно|одного)\s+(?:tv|display|screen|телевизор\w*|экран\w*)\b", text, re.I))
    return int(inputs.group(1)) if inputs else None, int(outputs.group(1)) if outputs else (1 if one_display else None)


def is_usb_matrix_request(text: str) -> bool:
    """USB peripheral routing, not HDMI/video matrix or KVM switching."""
    if not re.search(r"\busb(?:\s*3(?:\.2)?|\s*2)?\b", text, re.I):
        return False
    explicit_usb_only = bool(re.search(r"\busb[ -]?only\b|\bno\s+video\b", text, re.I))
    if (re.search(r"\bkvm\b", text, re.I) and not explicit_usb_only
            and not re.search(r"\busb\b.{0,20}\bmatrix\b", text, re.I)):
        return False
    if not explicit_usb_only and re.search(r"\b(?:hdmi|video|display|monitor|screen|\d\s*k)\b", text, re.I):
        return False
    return bool(re.search(r"\busb\b.{0,35}\b(?:matrix|peripherals?|devices?)\b|"
                          r"\b(?:share|sharing|route|switch)\b.{0,45}\busb\b.{0,25}\b(?:devices?|peripherals?)\b|"
                          r"\b(?:matrix|peripherals?|devices?)\b.{0,35}\busb\b", text, re.I | re.S))


def requested_kvm_hosts(text: str) -> int | None:
    """Read host-computer count without treating USB devices as video outputs."""
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "eight": 8}
    match = re.search(r"\b(\d{1,2}|one|two|three|four|five|six|eight)\s*(?:computers?|pcs?|hosts?)\b", text, re.I)
    if match:
        value = match.group(1).lower()
        return int(value) if value.isdigit() else words[value]
    match = re.search(r"\b(\d{1,2})\s*[- ]?\s*port\s+kvm\b", text, re.I)
    return int(match.group(1)) if match else None


def requested_distance_m(text: str) -> float | None:
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*(km|kilometers?|met(?:er|re)s?|m|ft|feet)\b", text, re.I)
    if not match:
        return None
    value, unit = float(match.group(1)), match.group(2).lower()
    return value * (1000 if unit.startswith("k") else 0.3048 if unit in {"ft", "feet"} else 1)


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
    if product.get("stock_status") in {"Out of Stock", "Discontinued", "Not in Feed"}:
        return "product is not available for purchase"
    if product.get("site_category") == "Discontinued":
        return "product is discontinued"
    if product.get("category") == "accessory" or any(word in name for word in ("wall mount", "ceiling mount", "mounting bracket")):
        return "accessory, not primary equipment"
    if "NUTRIX" in sku and not MEDICAL_TERMS.search(text):
        return "medical-only camera outside a medical scenario"
    if "usb matrix" in cats:
        if interface.get("primary_fn") != "usb-matrix-switcher":
            return "USB peripheral matrix required"
    if sku == "BG-USM-44" and re.search(r"\b(?:hdmi|video|display|monitor|screen|8k|4k)\b", text, re.I):
        return "USB-only matrix does not route video"
    if "kvm" in cats and re.search(r"\b(?:hdmi|video|display|monitor|screen|8k|4k)\b", text, re.I):
        if not interface.get("in_hdmi_count") or not interface.get("out_hdmi_count"):
            return "HDMI video KVM required"
    if "kvm" in cats:
        hosts = requested_kvm_hosts(text)
        if hosts and (interface.get("in_hdmi_count") or product.get("inputs") or 0) < hosts:
            return "insufficient KVM host inputs"
    if re.search(r"\beARC\b", text, re.I):
        evidence = name + " " + (product.get("description") or "").lower()
        if "earc" not in evidence:
            return "eARC support required"
        if re.search(r"\b(?:av\s+)?receiver\b", text, re.I) and sku in {"BG-8K-AA", "BG-8K-SA"}:
            return "adapter is intended for an amplifier or soundbar, not an AV receiver"

    need_8k, need_4k120 = requested_video(text)
    need_4k = bool(re.search(r"\b4\s*k(?:\b|(?=\d))", text, re.I))
    need_4k60 = bool(re.search(r"\b4\s*k\s*(?:@|/|at)?\s*60\b", text, re.I))
    if (product.get("category") == "capture" and (need_8k or need_4k120)
            and re.search(r"\b(?:capture|record|stream)\b", text, re.I)
            and not re.search(r"\b(?:input|loop.?out|pass.?through)\b", text, re.I)):
        if (interface.get("max_res") or "").upper() not in ({"8K60", "8K30"} if need_8k else {"4K120", "8K30", "8K60"}):
            return "capture output resolution is below the requested format"
    video_device = not cats or any(term in cats for term in ("switch", "matrix", "splitter", "distribution", "camera", "encoder", "decoder", "extender", "av over ip"))
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

    if "splitter" in cats or "distribution amp" in cats:
        if interface.get("primary_fn") != "splitter":
            return "video splitter required"
        inputs, outputs = requested_ports(text)
        if inputs and (interface.get("in_hdmi_count") or 0) < inputs:
            return "insufficient HDMI inputs"
        if outputs and (interface.get("out_hdmi_count") or 0) < outputs:
            return "insufficient HDMI outputs"

    if "extender" in cats or product.get("category") == "extender":
        distance = requested_distance_m(text)
        if distance and (product.get("max_distance_m") or 0) < distance:
            return "insufficient extension distance"

    if ("switcher" in cats or "matrix" in cats) and "usb matrix" not in cats:
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
        if (interface.get("primary_fn") == "multiviewer"
                and "multiview" not in text.lower() and "video wall" not in text.lower()):
            return "multiviewer was not requested"
        if product.get("category") == "presentation_switcher" and "presentation" not in text:
            return "presentation switcher was not requested"
    return None


def rank_product(product: dict, interface: dict | None, text: str) -> tuple:
    """Prefer the closest port count after hard requirements pass."""
    interface = interface or {}
    inputs, outputs = requested_ports(text)
    if product.get("category") == "kvm_switch" and not inputs:
        inputs = requested_kvm_hosts(text)
    distance = requested_distance_m(text)
    return (
        max(0, (interface.get("out_hdmi_count") or 0) - outputs) if outputs else 0,
        max(0, (interface.get("in_hdmi_count") or 0) - inputs) if inputs else 0,
        max(0, (product.get("max_distance_m") or 0) - distance) if distance else 0,
        product.get("price_usd") or 0,
    )


def camera_family_key(sku: str) -> str:
    """Keep signal/technology suffixes while collapsing zoom and color variants."""
    sku = re.sub(r"-31$", "", sku.upper())
    sku = re.sub(r"-(B|W|S|G)$", "", sku.upper())
    sku = re.sub(r"\d{1,2}X(?=-|$)", "ZX", sku)
    return re.sub(r"-(10|12|20|25|30|31)(?=HSU|HSP|X)", "-Z", sku)


def camera_family_variants(conn, sku: str) -> list[dict]:
    key = camera_family_key(sku)
    if key == sku.upper():
        return []
    variants = []
    for row in conn.execute("""SELECT id, product_url, price_usd, stock_status FROM products
                               WHERE category='camera' AND (site_category IS NULL OR site_category != 'Discontinued')
                               AND (stock_status IS NULL OR stock_status NOT IN ('Discontinued', 'Out of Stock', 'Not in Feed'))"""):
        if camera_family_key(row["id"]) == key:
            variants.append(dict(row))
    return sorted(variants, key=lambda item: item["id"])
