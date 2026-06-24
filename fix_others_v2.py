import sys; sys.stdout.reconfigure(encoding='utf-8')
import sqlite3

conn = sqlite3.connect("products.db")

fixes = [
    # (id, category)
    ("BG-4P1TE",        "network"),         # 5-Port Gigabit Unmanaged POE Switch
    ("BG-FS8260",       "network"),          # 8-Port PoE+ Switch
    ("NET-00HN43",      "network"),          # Netgear Multi-Gig Switch
    ("BG-AVOIP1080D",   "encoder_decoder"),  # HD Video over IP Decoder
    ("BG-HAVS",         "encoder_decoder"),  # H.264/265 HDMI Streaming Encoder
    ("BG-STREAM-D",     "encoder_decoder"),  # IP/UVC to HDMI Decoder
    ("BG-STREAM-E",     "encoder_decoder"),  # HDMI to IP Encoder
    ("BG-STREAM-ND",    "encoder_decoder"),  # IP/UVC to HDMI Decoder (NDI)
    ("BG-STREAM-NE",    "encoder_decoder"),  # HDMI to IP Encoder (NDI)
    ("BG-BPTZ-10XU",    "camera"),           # USB Huddle Room Camera
    ("BG-BPTZ-3XU",     "camera"),           # USB Huddle Room Camera
    ("BG-BWEB-S",       "camera"),           # USB Web Camera
    ("BG-BWEB-W",       "camera"),           # USB Web Camera
    ("BG-CAM-USB4K",    "camera"),           # 4K USB Conference Camera
    ("BG-PACKSHOT-C10X","camera"),           # Vertical Box Camera
    ("BG-HDVS42U",      "switcher"),         # 4-Channel Streaming Switcher Mixer
    ("BG-UHM",          "switcher"),         # USB/HDMI Camera Video Selector
    ("BG-CONNEXIO",     "presentation_switcher"),  # BYOD Wireless Collaboration
    ("BG-C-USB",        "accessory"),        # USB Flash Drive for Connexio
    ("BG-EXM-SM5",      "audio"),            # Extension Mic
    ("BG-VOP-ACC-RM10", "accessory"),        # Rack for VOP-MT
    ("BG-VOP-CB",       "controller"),       # Smart Controller for VOP-MT
    ("SFP-MM2LC-F",     "accessory"),        # SFP Module
    ("SFP-SM1LC-F",     "accessory"),        # SFP Module
    ("SFP-SM1LC-FC",    "accessory"),        # SFP Module
]

for pid, cat in fixes:
    conn.execute("UPDATE products SET category=? WHERE id=?", (cat, pid))
    row = conn.execute("SELECT title FROM products WHERE id=?", (pid,)).fetchone()
    title = row[0][:50] if row else "NOT FOUND"
    print(f"  {pid:<20} -> {cat:<20} ({title})")

conn.commit()

# Verify
remaining = conn.execute("SELECT COUNT(*) FROM products WHERE category='other'").fetchone()[0]
total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
print(f"\nRemaining 'other': {remaining}")
print(f"Total products: {total}")

# Final category summary
print("\nFinal category breakdown:")
for row in conn.execute("SELECT category, COUNT(*) n FROM products GROUP BY category ORDER BY n DESC"):
    print(f"  {row[0]:<25} {row[1]:>4}")

conn.close()
