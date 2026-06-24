"""Manually correct 'other' category products."""
import sqlite3

conn = sqlite3.connect("products.db")

fixes = [
    # (id, category, inputs, outputs, notes)
    ("BG-3GSH",         "sdi",                   1, 1,    "3G-SDI to HDMI converter"),
    ("BG-4K120CHA",     "capture",               1, 1,    "USB-C 4K120 capture box with HDMI loopout, scaler"),
    ("BG-4KBHS",        "sdi",                   1, 1,    "12G/6G/3G/HD-SDI & HDMI 2.0 bi-directional converter"),
    ("BG-4KBHS-PRO",    "sdi",                   1, 1,    "HDMI 2.0 & 12G-SDI cross converter and scaler with LCD display"),
    ("BG-4KCH",         "capture",               1, 1,    "4K UHD USB-C video capture device with scaler"),
    ("BG-4KCHA",        "capture",               1, 1,    "USB-C 4K60 capture card with HDMI loopout and scaler"),
    ("BG-CJ-IPRSPRO",   "controller",            None, None, "Professional IP/RS-232/422/485 joystick controller for PTZ cameras"),
    ("BG-COMMANDER-PRO","controller",            None, None, "Professional IP joystick controller with 7-inch touchscreen"),
    ("BG-CONNEXIO",     "presentation_switcher", None, None, "4K BYOD collaboration solution with AirPlay, Miracast, Chromecast"),
    ("BG-SC-GRHU",      "accessory",             None, None, "HDMI/USB 3.0 table grommet accessory for BG-UHD-KVM41"),
    ("BG-VOP-MT",       "av_over_ip",            1, 1,    "4K HDMI 2.0 AV over IP multicast transceiver with video wall and PoE"),
]

for product_id, category, inputs, outputs, notes in fixes:
    conn.execute("""
        UPDATE products SET category=?, inputs=?, outputs=?, notes=?
        WHERE id=?
    """, (category, inputs, outputs, notes, product_id))
    print(f"  {product_id} -> {category}")

conn.commit()

# Verify
print("\nVerified:")
for row in conn.execute("SELECT id, category, inputs, outputs FROM products WHERE id IN ({})".format(
    ",".join(f"'{pid}'" for pid, *_ in fixes)
)):
    print(f"  {row}")

conn.close()
print("\nDone.")
