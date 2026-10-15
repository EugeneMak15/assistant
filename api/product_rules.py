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
    outputs = re.search(r"\b(\d{1,2})\s*(?:tvs?|displays?|screens?|monitors?|outputs?|монитор\w*|экран\w*|телевизор\w*)\b", text, re.I)
    one_display = bool(re.search(r"\b(?:one|single|один|одно|одного)\s+(?:tv|display|screen|телевизор\w*|экран\w*)\b", text, re.I))
    distinct_home_displays = bool(re.search(r"\bprojector\b.*\btv\b.*\btv\b", text, re.I | re.S))
    return int(inputs.group(1)) if inputs else None, int(outputs.group(1)) if outputs else (3 if distinct_home_displays else 1 if one_display else None)


def is_usb_matrix_request(text: str) -> bool:
    """USB peripheral routing, not HDMI/video matrix or KVM switching."""
    if re.search(r"\bkeyboard\b", text, re.I) and re.search(r"\bmouse\b", text, re.I) and requested_kvm_hosts(text) and not re.search(r"\b(?:hdmi|video|display|monitor|screen|kvm)\b", text, re.I):
        return True
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
                          r"\b(?:matrix|peripherals?|devices?)\b.{0,35}\busb\b|"
                          r"\b(?:share|sharing)\b.{0,70}\b(?:webcam|keyboard|mouse)\b.{0,70}\busb[ -]?c\b", text, re.I | re.S))


def requested_kvm_hosts(text: str) -> int | None:
    """Read host-computer count without treating USB devices as video outputs."""
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "eight": 8}
    match = re.search(r"\b(\d{1,2}|one|two|three|four|five|six|eight)\s*(?:usb[ -]?c\s*)?(?:computers?|pcs?|hosts?|laptops?)\b", text, re.I)
    if match:
        value = match.group(1).lower()
        return int(value) if value.isdigit() else words[value]
    match = re.search(r"\b(\d{1,2})\s*[- ]?\s*port\s+kvm\b", text, re.I)
    return int(match.group(1)) if match else None


def requested_distance_m(text: str) -> float | None:
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*(km|kilometers?|kil[oó]metros?|met(?:er|re)s?|metros?|m|ft|feet|pies?)\b", text, re.I)
    if not match:
        return None
    value, unit = float(match.group(1)), match.group(2).lower()
    return value * (1000 if unit.startswith("k") else 0.3048 if unit in {"ft", "feet", "pie", "pies"} else 1)


def requested_wall_screens(text: str) -> int | None:
    rows = re.search(r"\b(\d+)\s+rows?\s+of\s+(\d+)\s+(?:tvs?|screens?|displays?)\b", text, re.I)
    if rows:
        return int(rows.group(1)) * int(rows.group(2))
    layout = re.search(r"\b(\d+)\s*[x×]\s*(\d+)\s+(?:video\s+)?wall\b", text, re.I)
    if not layout and "wall" in text.lower() and "matrix" not in text.lower():
        layout = re.search(r"\b(\d+)\s*[x×]\s*(\d+)\b", text, re.I)
    return int(layout.group(1)) * int(layout.group(2)) if layout else None


def mentioned_catalog_skus(conn, text: str) -> list[str]:
    """Resolve explicit model/series names without guessing from generic specs."""
    normalized = " " + " ".join(re.findall(r"[A-Z0-9]+", text.upper())) + " "
    matches = []
    accessory_request = bool(re.search(r"\b(?:mount|mounting|bracket|rack kit|rackmount|accessor(?:y|ies))\b", text, re.I))
    for sku, category in conn.execute(
        "SELECT id, category FROM products WHERE (site_category IS NULL OR site_category!='Discontinued') "
        "AND (stock_status IS NULL OR stock_status NOT IN ('Discontinued','Out of Stock','Not in Feed')) "
        "ORDER BY id"
    ):
        if (category == "accessory" or sku.endswith("-EXT")) and not accessory_request:
            continue
        parts = sku.upper().split("-")
        if len(parts) < 2:
            continue
        full = " " + " ".join(parts) + " "
        if full in normalized:
            matches.append(sku)
            continue
        family = parts[1]
        if family == "IPGEAR" and len(parts) > 2:
            alias = " IPGEAR " + parts[2] + " "
        elif len(family) >= 5 and family.isalpha():
            alias = " " + family + " "
        else:
            continue
        if alias in normalized:
            matches.append(sku)
    return matches


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
    accessory_request = bool(re.search(r"\b(?:mount|mounting|bracket|rack kit|rackmount|accessor(?:y|ies))\b", text, re.I))
    if (product.get("category") == "accessory" or any(word in name for word in ("wall mount", "ceiling mount", "mounting bracket"))) and not accessory_request:
        return "accessory, not primary equipment"
    if product.get("category") == "accessory":
        if re.search(r"\bipgear[ -]?ultra\b", text, re.I) and "IPGEAR-ULTRA" not in sku:
            return "accessory for the wrong product line"
        if re.search(r"\bipgear[ -]?pro\b", text, re.I) and "IPGEAR-PRO" not in sku:
            return "accessory for the wrong product line"
        if re.search(r"\b(?:10\s*(?:units?|pcs?)|for\s+10)\b", text, re.I) and "RM10" not in sku:
            return "rack kit capacity below 10 units"
        if "rack" in text and "rack" not in name.lower():
            return "rack accessory required"
        if "ceiling" in text and "ceiling" not in name.lower():
            return "ceiling mount required"
    if re.search(r"\b(?:one box|all[ -]?in[ -]?one)\b", text, re.I) and re.search(r"\b(?:video|production)\s+switcher\b", text, re.I) and re.search(r"\b(?:ptz\s+)?joystick\b", text, re.I):
        if not (interface.get("in_hdmi_count") or 0) >= 4 or not interface.get("ctrl_visca"):
            return "integrated video switcher and PTZ joystick required"
    if re.search(r"\btaa(?:[ -]compliant)?\b", text, re.I) and product.get("taa_compliant") != 1:
        return "TAA compliance not verified on the official product list"
    if "NUTRIX" in sku and not MEDICAL_TERMS.search(text):
        return "medical-only camera outside a medical scenario"
    if ("audio converter" in cats or "audio extractor" in cats or "earc adapter" in cats) and product.get("category") != "audio":
        return "dedicated audio converter required"
    if "camera" in cats and "bundle" not in cats and product.get("category") != "camera":
        return "standalone PTZ camera required"
    if "videobar" in cats and "extension microphone" in name:
        return "video bar required, not its microphone accessory"
    is_extender = product.get("category") == "extender" or "extender" in cats
    if is_extender:
        if re.search(r"\bwall[ -]?plate\b", text, re.I) and not (
            "wall plate" in name or interface.get("form_factor") == "wall plate"
        ):
            return "wall-plate form factor required"
        if re.search(r"\busb[ -]?c\b", text, re.I) and "usb-c" not in name and "usb-c" not in (product.get("description") or "").lower():
            return "USB-C host input required"
        if re.search(r"\bwall[ -]?plate\s+kvm\b", text, re.I) and "kvm" not in name and "kvm" not in (product.get("description") or "").lower():
            return "wall-plate KVM capability required"
        if re.search(r"\busb\s*3(?:\.\d)?\b", text, re.I):
            evidence = " ".join((name, (product.get("description") or "").lower(), " ".join(_json_list(product.get("features"))).lower()))
            if not re.search(r"\busb\s*3(?:\.\d)?\b", evidence, re.I):
                return "USB 3.x extension required"
        if re.search(r"\bdual[ -]?host\b", text, re.I) and (product.get("inputs") or 0) < 2:
            return "two USB hosts required"
        if re.search(r"\btwo\s+usb[ -]?c\s+laptops?\b", text, re.I) and re.search(r"\btwo\s+4k\s+screens?\b", text, re.I):
            if (product.get("inputs") or 0) < 2 or (interface.get("out_hdmi_count") or 0) < 2:
                return "integrated dual-host, dual-display extender required"
            if "usb" not in name:
                return "USB peripheral extension required"
        if re.search(r"\b(?:3g|6g|12g)?[ -]?sdi\b", text, re.I) and not interface.get("in_sdi"):
            return "SDI input required"
        if re.search(r"\bhdmi\b", text, re.I) and not interface.get("in_hdmi"):
            return "HDMI input required"
        if re.search(r"\bfib(?:er|re)\b", text, re.I) and not interface.get("out_fiber"):
            return "fiber extension required"
        if re.search(r"\busb\b.{0,25}\bfib(?:er|re)\b|\bfib(?:er|re)\b.{0,25}\busb\b", text, re.I):
            if "usb" not in name and "usb" not in (product.get("description") or "").lower():
                return "USB over fiber required"
    if re.search(r"\b(?:quad[ -]?view|multiview)\b", text, re.I) and re.search(r"\busb\s+capture\b", text, re.I):
        if not interface.get("out_usb_video"):
            return "USB capture output required"
        if (interface.get("in_hdmi_count") or product.get("inputs") or 0) < 4:
            return "four video inputs required for quad-view"
        evidence = name + " " + (product.get("description") or "").lower()
        if not re.search(r"quad[ -]?view|multiview", evidence):
            return "quad-view processing required"
    dante_device = not re.search(r"\bdante\s+(?:dsp|audio\s+processor)\b", text, re.I) or product.get("category") == "audio"
    if dante_device and re.search(r"\bdante\b", text, re.I) and product.get("category") in {"switcher", "presentation_switcher", "camera", "audio"}:
        if not (interface.get("out_dante") or interface.get("in_dante")):
            return "Dante support required"
    if is_extender and re.search(r"\bloop[ -]?out\b", text, re.I):
        evidence = " ".join((name, (product.get("description") or "").lower(), " ".join(_json_list(product.get("features"))).lower()))
        if not re.search(r"\bloop[ -]?out\b", evidence):
            return "HDMI loop-out required"
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
    if re.search(r"\beARC\b", text, re.I) and product.get("category") == "audio":
        evidence = name + " " + (product.get("description") or "").lower()
        if "earc" not in evidence:
            return "eARC support required"
        if re.search(r"\b(?:av\s+)?receiver\b", text, re.I) and sku in {"BG-8K-AA", "BG-8K-SA"}:
            return "adapter is intended for an amplifier or soundbar, not an AV receiver"
        if "soundbar" in text.lower() and sku == "BG-8K-AA":
            return "HDMI soundbar output required"

    need_8k, need_4k120 = requested_video(text)
    need_4k = bool(re.search(r"\b4\s*k(?:\b|(?=\d))", text, re.I))
    need_4k60 = bool(re.search(r"\b4\s*k\s*(?:@|/|at)?\s*60\b", text, re.I))
    if (product.get("category") == "capture" and (need_8k or need_4k120)
            and re.search(r"\b(?:capture|record|stream)\b", text, re.I)
            and not re.search(r"\b(?:input|loop.?out|pass.?through)\b", text, re.I)):
        if (interface.get("max_res") or "").upper() not in ({"8K60", "8K30"} if need_8k else {"4K120", "8K30", "8K60"}):
            return "capture output resolution is below the requested format"
    video_device = not cats or any(term in cats for term in ("switch", "matrix", "splitter", "distribution", "camera", "encoder", "decoder", "extender", "av over ip", "generator", "tester", "video wall", "videowall", "video processor"))
    if video_device and need_8k:
        evidence = name + " " + " ".join(_json_list(product.get("features"))).lower()
        if interface.get("supports_8k") != 1 or "8K" not in evidence.upper():
            return "8K required"
    wall_input_only_alternative = ("video wall" in cats or "videowall" in cats) and sku in {"BG-UHD-VWP-1X4", "BG-UHD-VW2X2"} and not re.search(r"\b4k\s*(?:60\s*)?output|\bnative\s+4k\b", text, re.I)
    if video_device and need_4k and interface.get("supports_4k") != 1 and not wall_input_only_alternative:
        return "4K required"
    if video_device and need_4k60 and (interface.get("max_res") or "").upper() in {"1080P", "1080P60", "4K30"} and not wall_input_only_alternative:
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
        signal = "sdi" if re.search(r"\b(?:3g|6g|12g)?[ -]?sdi\b", text, re.I) else "hdmi"
        if signal == "sdi" and re.search(r"\b12g[ -]?sdi\b", text, re.I):
            evidence = " ".join((sku, name, (product.get("description") or "").lower()))
            if not re.search(r"\b12g[ -]?sdi\b|12gs", evidence, re.I):
                return "12G-SDI support required"
        if inputs and (interface.get(f"in_{signal}_count") or 0) < inputs:
            return f"insufficient {signal.upper()} inputs"
        if outputs and (interface.get(f"out_{signal}_count") or 0) < outputs:
            return f"insufficient {signal.upper()} outputs"

    if "extender" in cats or product.get("category") == "extender":
        distance = requested_distance_m(text)
        if distance and (product.get("max_distance_m") or 0) < distance:
            return "insufficient extension distance"
    if "video wall" in cats or "videowall" in cats:
        wall_evidence = " ".join((name, product.get("what_it_does") or "", " ".join(_json_list(product.get("features"))))).lower()
        if not re.search(r"video[ -]?wall", wall_evidence):
            return "video-wall image processing required"
        screens = requested_wall_screens(text)
        if screens and (interface.get("out_hdmi_count") or product.get("outputs") or 0) < screens:
            return "insufficient video-wall outputs"

    if ("switcher" in cats or "matrix" in cats) and "usb matrix" not in cats:
        if product.get("category") not in {"switcher", "presentation_switcher"}:
            return "wrong switcher category"
        inputs, outputs = requested_ports(text)
        available_inputs = (product.get("inputs") or 0) if product.get("category") == "presentation_switcher" else (interface.get("in_hdmi_count") or 0)
        if inputs and available_inputs < inputs:
            return "insufficient HDMI inputs"
        if outputs and (interface.get("out_hdmi_count") or 0) < outputs:
            return "insufficient HDMI outputs"
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
    outputs = requested_wall_screens(text) or outputs
    if product.get("category") == "kvm_switch" and not inputs:
        inputs = requested_kvm_hosts(text)
    distance = requested_distance_m(text)
    requested_zoom = re.search(r"\b(\d{1,2})\s*x\s*(?:zoom)?\b", text, re.I)
    zoom_gap = 0
    resolution_overkill = 0
    movement_overkill = 0
    if product.get("category") == "camera" and re.search(r"\b(?:fixed|static)\s+(?:camera|shots?)\b", text, re.I) and "ptz" not in text.lower():
        movement_overkill = int(interface.get("primary_fn") == "camera-ptz")
    if product.get("category") == "camera" and re.search(r"\b1080\s*p?\b", text, re.I) and not re.search(r"\b4\s*k\b", text, re.I):
        resolution_overkill = int(bool(interface.get("supports_4k")))
    if (product.get("category") == "camera" or str(interface.get("primary_fn", "")).startswith("camera-")) and requested_zoom:
        optical = interface.get("zoom_optical") or 0
        zoom_gap = abs(optical - int(requested_zoom.group(1))) if optical else 999
    return (
        movement_overkill,
        resolution_overkill,
        zoom_gap,
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
