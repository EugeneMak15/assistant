# Product AI on Dev

This feature is separate from the general Advisor. It answers questions about the WooCommerce product on the open page, including every published variation of a variable product. It does not compare or recommend products.

## Components

- `wordpress/`: Dev-only WooCommerce plugin. It places an AI button after the product title, collects the current product's descriptions, specifications, interfaces, resources, attributes and variations, and serves an anonymous rate-limited AJAX endpoint.
- `app.py`: loopback-only FastAPI service on port 8002, running as `advisor`. It uses the existing OpenAI key from `/opt/assistant/.env` and exact-SKU matching only.
- `docs_index.py`: lazily indexes locally attached PDFs in an isolated FTS database (`/opt/product-assistant-dev/product_docs.db`). Attached diagram images are described once and cached. Live Dev blog/KB articles mentioning the exact SKU are also supplied by WordPress. The older Advisor Chroma data is supplemental, not authoritative when it conflicts with the current product page.

The Dev site currently uses Basic Auth and blocks `wp_remote_post` in migration preview, so the plugin talks to the loopback service with a fixed-address cURL call. The chat uses `admin-ajax.php` because Dev Basic Auth is interpreted as invalid WordPress application-password credentials on REST requests. Neither protection is disabled.

## Deploy

Install the Python files as `advisor` in `/opt/product-assistant-dev`, install `pypdf` to `/opt/product-assistant-dev/vendor`, install the unit file as `/etc/systemd/system/bzb-product-assistant-dev.service`, and enable the unit. Install `wordpress/` into the Dev-only plugin directory `wp-content/plugins/bzb-product-ai-dev` and activate it on `dev.bzbgear.com`. Do not push to `main`: the existing GitHub Action deploys `main` to production Advisor. This code lives on branch `codex/product-assistant-dev` until reviewed.

## Verified 2026-11-05

- BG-8KCH: answers HDMI/USB resolution, EDID, manual and diagram links, with source citations.
- BG-8KCH: refuses a question about BG-ADAMO-4K.
- BG-IPGEAR-PRO: recognizes transmitter and receiver variations.
- FTS has 43 document chunks for BG-8KCH; diagram description cached from its attached PNG.
- Dev service health and WordPress AJAX handler passed; the button and drawer rendered on the Dev product page in Chrome.

The final live-browser AJAX retest was blocked by invalid credentials in the existing Dev Basic Auth browser session. Internal AJAX handler testing passed, but a fresh browser test after Dev authentication is restored remains necessary.
