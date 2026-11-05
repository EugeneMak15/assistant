"""Read-only live Google Shopping feed comparison for seven new SKUs."""
import urllib.request
import xml.etree.ElementTree as ET

url = "https://bzbgear.com/wp-content/uploads/woo-feed/google/xml/bzbgearshoppingfeed.xml"
with urllib.request.urlopen(url, timeout=30) as response:
    root = ET.fromstring(response.read())
targets = {"BG-4K-VP1616PRO", "BG-IPGEAR-PRO", "BG-IPGEAR-PRO-T", "BG-IPGEAR-PRO-R",
           "BG-UHD-VWP110L", "BG-EXH-8K100U", "BG-EXH-8K50C", "BG-EXH-4KFE", "BG-8KCH"}
for item in root.iter("item"):
    fields = {node.tag.split("}")[-1]: (node.text or "") for node in item}
    sku = fields.get("id", "")
    if sku in targets:
        print(sku, fields.get("availability", ""), fields.get("link", ""), len(fields.get("description", "")))
        if sku == "BG-UHD-VWP110L":
            print("description_sample", fields.get("description", "")[:400].replace("\n", " "))
