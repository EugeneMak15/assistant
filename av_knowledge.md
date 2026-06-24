# BZB Gear AV Knowledge Base
# For use by the AI recommendation engine — authoritative reference for signal chains,
# compatibility rules, and installation best practices.

---

## 1. SIGNAL TYPES & BANDWIDTH

### Bandwidth table (memorize these — they determine what resolution is achievable)

| Signal        | Bandwidth  | Max Resolution  | Notes |
|---------------|-----------|-----------------|-------|
| HDMI 1.4      | 10.2 Gbps | 4K30 or 1080p60 | Most common legacy standard |
| HDMI 2.0      | 18 Gbps   | 4K60 HDR        | Current standard for 4K |
| HDMI 2.1      | 48 Gbps   | 8K60 / 4K120    | Gaming, future-proof |
| DisplayPort 1.2 | 17.28 Gbps | 4K60           | PC monitors |
| DisplayPort 1.4 | 32.4 Gbps | 8K30 / 4K120   | High-end workstations |
| USB-C (DP Alt)| 32.4 Gbps | 8K30 / 4K120    | Depends on cable quality |
| SDI (3G-SDI)  | 2.97 Gbps | 1080p60         | Broadcast standard |
| 6G-SDI        | 6 Gbps    | 4K30 (UHD)      | Transitional broadcast |
| 12G-SDI       | 11.88 Gbps | 4K60 (UHD)     | Modern broadcast 4K |
| HDBaseT 1.0   | 10.2 Gbps | 1080p / 4K30    | AV over Cat cable, max 100m |
| HDBaseT 2.0   | 18 Gbps   | 4K60            | Requires Cat6 or better |
| NDI (network) | Variable  | Up to 4K60      | Requires 1Gbps network per stream |
| Fiber         | 48 Gbps+  | 8K60            | Unlimited distance, immune to EMI |
| Dante         | ~1 Gbps   | Audio only      | Audio-over-IP, lossless |

### Resolution bandwidth requirements

| Resolution  | Required bandwidth | Minimum signal |
|-------------|-------------------|----------------|
| 1080p30     | 3 Gbps            | SDI, HDMI 1.4  |
| 1080p60     | 6 Gbps            | 3G-SDI, HDMI 1.4 |
| 4K30 (UHD)  | 9 Gbps            | HDMI 2.0, 6G-SDI |
| 4K60 (UHD)  | 18 Gbps           | HDMI 2.0, 12G-SDI, HDBaseT 2.0 |
| 4K120       | 40 Gbps           | HDMI 2.1 only  |
| 8K30        | 24 Gbps           | HDMI 2.1, Fiber |
| 8K60        | 48 Gbps           | HDMI 2.1, Fiber |

---

## 2. CABLE & DISTANCE RULES

### HDMI passive cables
- Up to 3m: any cable works
- 3–10m: certified High Speed HDMI (18Gbps) required for 4K60
- 10–15m: active HDMI cable required
- Over 15m: HDMI will NOT work — use extender, fiber, or HDBaseT

### HDBaseT (Cat cable) — BZB Gear extender series
- Cat5e: max 70m for 1080p; max 40m for 4K60
- Cat6: max 100m for 1080p; max 70m for 4K60
- Cat6A/7: max 100m for 4K60 (HDBaseT 2.0)
- RULE: Always use shielded (STP/FTP) Cat cable in environments with EMI (factories, broadcast)
- RULE: Do not run Cat cable parallel to power cables — minimum 15cm separation

### SDI coaxial cables
- 3G-SDI (1080p): up to 100m on RG6, up to 300m on RG11
- 12G-SDI (4K60): up to 80m on RG6 (Belden 1694A or equivalent)
- Over 100m: use SDI distribution amp to re-clock and boost signal
- RULE: Use Belden 1694A or equivalent for 12G-SDI — standard RG6 may fail at 4K

### Fiber optic
- Single-mode: effectively unlimited distance (km)
- Multi-mode: up to 550m typical
- Use case: buildings over 100m, outdoor runs, EMI-heavy environments
- BZB Gear products using fiber: BG-IPGEAR-ULTRA, BG-UHD-MVS21A/41A/42MA

### Wireless HDMI (BZB Gear BG-AIR4KAST series)
- Max range: 50m (line of sight)
- Max resolution: 4K60
- Latency: ~1 frame — unsuitable for KVM, gaming, camera monitoring requiring <1ms
- Cannot pass through walls reliably — requires line of sight
- Not suitable for permanent mission-critical installations

---

## 3. SIGNAL COMPATIBILITY RULES

### Direct connection compatibility
```
HDMI 2.1 → HDMI 2.0 input: OK (downgrades to 18Gbps)
HDMI 2.0 → HDMI 1.4 input: OK (downgrades to 10.2Gbps, loses 4K60)
12G-SDI  → 3G-SDI input:   OK (downgrades to 1080p60)
3G-SDI   → 12G-SDI input:  OK (full backward compatibility)
SDI      → HDMI:           REQUIRES CONVERTER (BG-B20HS or dedicated SDI→HDMI converter)
HDMI     → SDI:            REQUIRES CONVERTER
NDI      → HDMI:           REQUIRES DECODER (BG-STREAM-D or similar)
HDMI     → NDI:            REQUIRES ENCODER
Dante    → analog audio:   REQUIRES DANTE CONTROLLER + audio interface
```

### Cannot connect directly — always need conversion
- SDI ↔ HDMI: need bidirectional converter
- NDI ↔ SDI: need encoder/decoder
- Fiber ↔ HDMI: need SFP transceiver module
- HDBaseT ↔ HDMI: need transmitter (TX) and receiver (RX) balun pair
- Analog ↔ Digital: need ADC/DAC converter

---

## 4. BZB GEAR PRODUCT FAMILIES

### PTZ Cameras — ADAMO Series (4K, SDI + HDMI + NDI)
**When to use:** Broadcast studios, houses of worship, sports venues, streaming production

| SKU pattern | Zoom | Signals | Resolution | Key feature |
|-------------|------|---------|------------|-------------|
| BG-ADAMO-4K12X | 12x | 12G-SDI + HDMI 2.0 + NDI + USB + Dante | 4K60 | Auto-tracking |
| BG-ADAMO-4K25X | 25x | 12G-SDI + HDMI 2.0 + NDI + USB + Dante | 4K60 | Long zoom |
| BG-ADAMO-4K31X | 31x | 12G-SDI + HDMI 2.0 + NDI + USB + Dante | 4K60 | Maximum zoom |
| BG-ADAMO-4KND* | 12/25/31x | 12G-SDI + HDMI 2.0 + NDI | 4K60 | NDI|HX3 native |
| BG-ADAMO-4KDA* | 12/25/31x | 12G-SDI + HDMI 2.0 | 4K60 | SDI+HDMI only |

**SKU suffix guide:**
- `-W` = White, `-B` = Black
- `-31` = 31x zoom variant
- `ND` = NDI|HX3 built-in, `DA` = SDI+HDMI only

**ADAMO camera connection rules:**
- HDMI output: connect directly to HDMI switcher (BG-4K-44MA, BG-4K-88MA, BG-4K-1616MA)
- 12G-SDI output: connect to SDI distribution amp (BG-12GCSA) or SDI matrix, NOT to HDMI equipment without converter
- NDI output: requires 1Gbps network switch (see BG-IPGEAR-ULTRA-ACC-* network switches)
- USB output: for video conferencing software only (Zoom, Teams, OBS) — low latency, no HDBaseT compatible
- Always pair cameras with a PTZ controller (BG-COMMANDER series)
- Power via PoE++ (IEEE 802.3bt) or 12V DC — verify switch supports PoE++

### PTZ Cameras — Standard Series
**BG-4KPTZ-12XUHP:** 12x zoom, HDMI only, 4K60. Good entry-level. No SDI.
**BG-NUTRIX:** Medical-grade NDI PTZ, IEC 60601 certified. Use ONLY in medical environments.

### Matrix Switchers — BG-4K Series (HDMI 2.0)
**When to use:** Multi-source to multi-display routing, conference rooms, control rooms, sports bars

| SKU | Config | Bandwidth | Max Resolution |
|-----|--------|-----------|----------------|
| BG-4K-44MA | 4×4 | 18Gbps | 4K60 |
| BG-4K-88MA | 8×8 | 18Gbps | 4K60 |
| BG-4K-1616MA | 16×16 | 18Gbps | 4K60 |
| BG-4K-VP44 | 4×4 | 18Gbps | 4K60 + video wall |
| BG-4K-VP44PRO | 4×4 | 18Gbps | 4K60 + video wall PRO |
| BG-4K-VP1616 | 16×16 | 18Gbps | 4K60 + video wall |

**HDMI Matrix rules:**
- Inputs/outputs are HDMI 2.0 — supports 4K60 HDR
- Cannot accept SDI directly — need HDMI→SDI converter at camera
- Supports CEC, EDID management — configure EDID to highest common resolution
- BG-4K-VP series has built-in video wall / multiviewer capability
- For RS-232 control from Crestron/AMX/Control4: use serial API (included in manuals)

### Signal Extenders (HDBaseT over Cat)
**When to use:** HDMI runs over 5m, in-wall installation, AV rack to display

| SKU pattern | Distance | Bandwidth | Key spec |
|-------------|----------|-----------|----------|
| BG-EXH-70C4 | 70m | 18Gbps (4K60) | Cat6, PoE |
| BG-EXH-100C4 | 100m | 18Gbps (4K60) | Cat6A |
| BG-EXH-150C | 150m | 10.2Gbps (1080p) | Cat5e/6 |
| BG-EXHKVM-70C | 70m | 18Gbps (4K60) | + USB/KVM |
| BG-AIR4KAST | 50m wireless | 4K60 | No cable needed |

**Extender rules:**
- TX (transmitter) goes at source, RX (receiver) goes at display — always sold as pairs
- Cat cable must be clean run — no keystone patch panels unless specified as HDBaseT-compatible
- Do not use flat/ribbon Cat cable — use solid core, not stranded
- PoE: extender RX can power display via PoE in some models

### SDI Distribution & Splitting — BG-3GS / BG-12GCSA
**When to use:** Splitting SDI signal from camera to multiple monitors/recorders

| SKU | Config | Signal | Resolution |
|-----|--------|--------|------------|
| BG-3GS12 | 1×2 split | 3G-SDI | 1080p60 |
| BG-3GS14 | 1×4 split | 3G-SDI | 1080p60 |
| BG-3GSH | 1×6 split | 3G-SDI | 1080p60 |
| BG-12GCSA | 1×2 split | 12G-SDI | 4K60 |

**SDI splitter rules:**
- 3G-SDI splitters (BG-3GS*) will downgrade 12G-SDI input to 1080p60
- For 4K SDI splitting: use BG-12GCSA only
- SDI splitters re-clock the signal — safe for long cable runs after the split
- Tally light pass-through: BG-ADAMO cameras have tally — verify splitter passes tally

### PTZ Controllers — BG-COMMANDER Series
**RULE: Every PTZ camera deployment needs a controller. Do not omit.**

| SKU | Protocol | Cameras | Preview | Best for |
|-----|----------|---------|---------|----------|
| BG-COMMANDER-JR | RS-232/422, IP | Up to 4 | No | Small systems |
| BG-COMMANDER | IP, RS-232/422, VISCA | Up to 7 | No | Mid-size |
| BG-COMMANDER-G2 | NDI, IP, VISCA | Multiple | Yes (NDI) | NDI workflows |
| BG-COMMANDER-PRO | IP, NDI, RS-232/422 | Multiple | Yes | Professional broadcast |
| BG-CJ-IPRSPRO | IP, RS-232 | Up to 7 | No | Compact panel |

**Controller connection:**
- IP cameras: connect via same network switch as cameras
- RS-232/422: direct cable from controller to camera (VISCA protocol)
- NDI cameras: controller and cameras on same 1Gbps network

### AV Over IP — BG-IPGEAR Series
**When to use:** >8 displays, distance >150m, campus-wide distribution, scalable systems

| SKU | Standard | Max Res | Distance | Network req |
|-----|----------|---------|----------|-------------|
| BG-IPGEAR-PRO-T/R | H.264/265 | 4K | 120m (Cat), unlimited (IP) | 1Gbps |
| BG-IPGEAR-ULTRA | 4K60 | 4K60 | 100m (Cat6), unlimited (fiber) | 1Gbps, multicast |
| BG-IPGEAR-ULTRA-C | Controller | — | — | Manages matrix |
| BG-IPGEAR-XTREME-W-T/R | HDMI 2.1 | 4K120 | Wall plate | 10Gbps |

**AV-over-IP rules:**
- Requires managed network switch with IGMP snooping + multicast enabled
- Each 4K60 stream needs dedicated 1Gbps bandwidth — calculate total load
- Latency: ~1 frame (acceptable for most installs, not for KVM/gaming)
- BG-IPGEAR-ULTRA-ACC-RM2: managed network switch purpose-built for IPGEAR
- Zero-config multicast with BG-IPGEAR-ULTRA-C controller

### Encoders & Decoders — BG-STREAM / BG-HAVS
**When to use:** Live streaming to YouTube/Facebook, IPTV, remote production

| SKU | Function | Protocols | Resolution |
|-----|----------|-----------|------------|
| BG-HAVS | Encoder | H.264/265, RTSP, RTMP | 1080p |
| BG-STREAM-D | Decoder | NDI, HDMI 2.0, Dante | 4K60 |
| BG-AVOIP1080D | Decoder | H.264 IP | 1080p |

### Network Switches — BG-IPGEAR-ULTRA-ACC Series
**Purpose-built for AV-over-IP — pre-configured with IGMP, multicast, jumbo frames**
- BG-IPGEAR-ULTRA-ACC-RM2: 24-port managed, rack mount, PoE+
- Use for IPGEAR-ULTRA deployments — removes network configuration complexity
- General IT network switches: can work but require manual IGMP snooping configuration

### KVM Switches — BG-8K-KVM / BG-UHD-KVM Series
**When to use:** Control multiple computers from single keyboard/mouse/monitor

| SKU | Config | Bandwidth | Hotkey switch |
|-----|--------|-----------|---------------|
| BG-8K-KVM21A | 2×1 | 48Gbps (8K60) | Yes |
| BG-8K-KVM41A | 4×1 | 48Gbps (8K60) | Yes |
| BG-8K-KVM22A | 4 computers × 2 monitors | 48Gbps | Yes |
| BG-UHD-KVM41A | 4×1 | 18Gbps (4K60) | Yes |
| BG-EXHKVM-70C | 2×1 + HDBaseT 70m | 18Gbps | Yes |

### Multiviewers & Video Walls — BG-UHD-VW / BG-MV
**When to use:** Security monitoring, broadcast confidence monitoring, multi-feed viewing

| SKU | Config | Output | Notes |
|-----|--------|--------|-------|
| BG-MV41A-G2 | 4-in 1-out multiview | HDMI 1.4 | PiP, quad view |
| BG-UHD-MVS21A | 2×1 seamless switch | HDMI 2.0 + Fiber | No frame drop on switch |
| BG-UHD-MVS41A | 4×1 seamless switch | HDMI 2.0 + Fiber | No frame drop |
| BG-UHD-VW24 | Video wall 2×2 | HDMI 2.0 | 4-display wall |

---

## 5. INSTALLATION TOPOLOGY PATTERNS

### Pattern A: Simple Switcher (1-8 sources, 1-4 displays, <5m runs)
```
Sources (PC/Camera/Media) → HDMI Matrix Switcher → Displays
                                    ↓
                             RS-232 / IP Control
```
**Products:** BG-4K-44MA, BG-4K-88MA
**Use when:** Conference room, small studio, sports bar section, classroom

### Pattern B: Switcher + HDBaseT Extenders (up to 100m runs)
```
Sources → HDMI Matrix Switcher → HDBaseT TX → [Cat6 cable, up to 100m] → HDBaseT RX → Display
```
**Products:** BG-4K-88MA + BG-EXH-70C4 or BG-EXH-100C4
**Use when:** Meeting rooms with ceiling-mounted projectors, digital signage, hotel lobbies

### Pattern C: Broadcast SDI Chain (cameras to production)
```
PTZ Camera (12G-SDI) → SDI Distribution Amp → SDI Router/Switcher → SDI Monitor / Recorder / Encoder
                              ↓
                     PTZ Controller (BG-COMMANDER-PRO)
```
**Products:** BG-ADAMO-4K* + BG-12GCSA + BG-COMMANDER-PRO
**Use when:** Broadcast studio, house of worship live production, sports broadcast
**Note:** Keep SDI in the SDI domain as long as possible — only convert to HDMI at final display

### Pattern D: NDI IP Production
```
PTZ Camera (NDI out) → 1Gbps Network Switch → NDI Decoder → Display
                              ↓
                       NDI Controller (BG-COMMANDER-G2)
                              ↓
                       vMix / OBS / TriCaster (software)
```
**Products:** BG-ADAMO-4K* (NDI model) + BG-IPGEAR-ULTRA-ACC-RM2 + BG-COMMANDER-G2
**Use when:** Software-defined production, streaming workflows, modern houses of worship

### Pattern E: AV-over-IP (large venues, 10+ displays)
```
Sources → IPGEAR-ULTRA Encoder (TX) → Managed 1Gbps Switch → IPGEAR-ULTRA Decoder (RX) → Display
                                              ↓
                                   IPGEAR-ULTRA-C Controller
```
**Products:** BG-IPGEAR-ULTRA-T + BG-IPGEAR-ULTRA-R + BG-IPGEAR-ULTRA-C + BG-IPGEAR-ULTRA-ACC-RM2
**Use when:** Campus distribution, 10+ displays, unlimited distance, video wall

### Pattern F: Conference Room (BYOD)
```
Laptop (HDMI/USB-C) → Presentation Switcher → Ceiling Projector / Display
                              ↓
                  USB-C / wireless (BG-AIR4KAST)
                              ↓
                  Video bar (camera + mic + speaker)
```
**Products:** Presentation switcher + BG-AIR4KAST (if wireless needed)

### Pattern G: SDI + HDMI Mixed (hybrid broadcast)
```
SDI Camera → SDI→HDMI Converter → HDMI Matrix Switcher → Display
HDMI Camera → direct →↑
```
**RULE:** Convert SDI to HDMI at the input of the switcher, not in the middle of the chain

### Pattern H: Camera System for HOW (House of Worship)
```
PTZ Cameras (3-5x) → Controller (BG-COMMANDER-PRO)
        ↓ HDMI
HDMI Matrix Switcher (BG-4K-88MA)
        ↓ HDMI
Stream Encoder (BG-HAVS) → YouTube/Facebook Live
        ↓ HDMI
Projector / LED Wall → Congregation
        ↓ NDI (optional)
Recording PC (OBS/vMix)
```

---

## 6. CRITICAL COMPATIBILITY RULES

### Resolution chain rule
**The weakest link determines the final resolution.**
Example: 4K60 camera → HDMI 2.0 switcher → HDMI 1.4 cable → 4K display = OUTPUT IS 4K30 (limited by cable)

### EDID management
- Always configure EDID on matrix switchers to the common supported resolution
- If one display is 1080p in a 4K system — set EDID to 1080p or use EDID emulator
- BG-4K-MA series has built-in EDID management

### HDR compatibility
- HDR requires HDMI 2.0a minimum AND HDR-capable display AND HDR source
- Every device in the chain must pass HDR metadata
- HDBaseT 1.0 does NOT pass HDR metadata — use HDBaseT 2.0 (Cat6A)

### 4K60 over HDBaseT
- Requires HDBaseT 2.0 or higher
- Requires Cat6A (shielded recommended)
- Maximum 40m on Cat6, 70m on Cat6A
- If distance > 70m and need 4K60: use fiber or AV-over-IP

### SDI rules
- 12G-SDI cameras (BG-ADAMO-4K) output 4K60 over single coax
- NEVER connect 12G-SDI to 3G-SDI input directly (signal will downgrade to 1080p)
- SDI maximum cable distance before re-clocking: 80m (12G), 100m (3G)
- SDI does NOT carry audio separately — Dante/audio must be separate

### NDI network rules
- Each NDI 4K stream requires dedicated 200Mbps on network
- Use 1Gbps switch minimum — BG-IPGEAR-ULTRA-ACC-RM2 recommended
- Enable IGMP snooping on switch to prevent multicast flooding
- NDI and corporate IT traffic should be on separate VLANs

### PoE for PTZ cameras
- BG-ADAMO cameras require PoE++ (IEEE 802.3bt, 60-90W) — standard PoE (15W) will NOT work
- Verify switch PoE budget: 4 cameras × 25W = 100W minimum switch budget
- Alternative: use 12V DC power supply included with camera

---

## 7. COMMON INSTALLER MISTAKES

1. **Using HDMI 1.4 cable for 4K60** — looks fine initially, fails intermittently. Always use Premium HDMI (18Gbps certified).

2. **Running Cat5e for 4K60 HDBaseT** — Cat5e max for 4K60 is 40m; installers assume 100m and get signal dropouts. Use Cat6.

3. **Forgetting PTZ controller** — cameras arrive, no way to pan/tilt/zoom. Always quote BG-COMMANDER-PRO with camera systems.

4. **Mixing 3G-SDI and 12G-SDI equipment without checking** — 12G-SDI camera into 3G-SDI splitter silently downgrades to 1080p with no error message.

5. **No EDID management on matrix switcher** — displays go blank when source resolution doesn't match. Set EDID to lowest common resolution in system.

6. **Using standard IT switch for NDI/AV-over-IP** — without IGMP snooping configured, multicast floods all ports and network collapses. Always use BG-IPGEAR-ULTRA-ACC-RM2 or configure IT switch manually.

7. **Wireless HDMI (BG-AIR4KAST) through walls** — it's line-of-sight. Through drywall may work, through concrete will not.

8. **SDI run without RG6 cable** — using generic coax (RG59) for SDI causes signal loss. Use Belden 1694A equivalent for all SDI runs.

9. **PoE budget exceeded** — adding 4th or 5th PoE++ camera causes all cameras to lose power or power cycle. Calculate total PoE budget before spec'ing switch.

10. **Daisy-chaining HDBaseT extenders** — NOT supported. Each extender must connect directly to switcher output. Cannot chain TX→RX→TX→RX.

11. **Control system (Crestron/AMX) serial wiring** — BZB Gear switchers use RS-232, not RS-485. Null modem may be required depending on control system output.

12. **Forgetting fiber SFP modules** — BG-IPGEAR-ULTRA and BG-UHD-MVS have fiber ports but SFP modules are sold separately. Always include BG-SFP-* in quote.

13. **Adding unnecessary signal converters** — If a device has multiple output types (e.g., a camera outputs BOTH 12G-SDI AND HDMI), connect via the output type that matches the next device DIRECTLY. Do NOT add a converter just because SDI is mentioned. Example: BG-ADAMO-4K12X has 12G-SDI + HDMI + NDI outputs — if the downstream device accepts HDMI, connect HDMI directly. Only use SDI→HDMI converter (BG-4KSH, BG-B20HS) when the camera has SDI output ONLY and the next device accepts HDMI only.

14. **Misreading signal_type in customer requirements** — If customer says "SDI cameras" but the camera model has HDMI output too, the HDMI output is still available. Choose the signal path that minimizes hardware: prefer direct connections, avoid conversion whenever the device supports the required signal natively.

15. **Recommending both color variants of the same product** — Products ending in -B (Black) and -W (White) are IDENTICAL except for chassis color. NEVER include both BG-XXXXX-B and BG-XXXXX-W in the same recommendation — this is redundant and looks unprofessional. Always pick ONE color variant. Default to -B (Black) unless the customer specifies a preference or the environment calls for white (e.g., white ceiling installation). Mention color options are available in a single note: "available in Black (-B) or White (-W)".

---

## 8. QUICK DECISION GUIDE

**How many displays?**
- 1-4 displays: simple switcher or splitter
- 4-16 displays: matrix switcher (BG-4K-88MA or BG-4K-1616MA)
- 16+ displays: AV-over-IP (BG-IPGEAR-ULTRA)

**Which network switch for AV-over-IP / NDI?**
All switches below are in the BZB Gear catalog. Always recommend from this list — do NOT invent switch model numbers.

| Scenario | Switch SKU | Why |
|---|---|---|
| Small NDI/IP system (≤8 devices, PoE cameras) | NET-M4250-10G2F-POE+PC | 8×1G PoE+ 125W, 2×SFP, AV preconfigured |
| Medium system (≤24 devices, PoE cameras) | NET-M4250-26G4F-POE+PC | 24×1G PoE+ 300W, 4×SFP, AV preconfigured |
| Large system (≤40 devices, PoE++ cameras) | NET-M4250-40G8XF-POE++PC | 40×1G PoE++ 90W/port 2880W total, 8×SFP+ |
| Large system (40 devices, lower PoE budget) | NET-M4250-40G8F-POE+PC | 40×1G PoE+ 480W, 8×SFP |
| High-bandwidth 10G fabric (AV-over-IP backbone) | NET-M4300-48X-PC | 48×10GbE, 4×SFP+, stackable L3 |
| 10G stackable (medium backbone) | NET-M4300-24X-PC | 24×10GbE, 4×SFP+ |
| Small unmanaged (conferencing, no multicast needed) | Use any standard unmanaged PoE+ switch (BG-FS8260 is discontinued) | 8-port 1G PoE+ with 2×SFP, simple install |

Rules:
- NDI and BG-IPGEAR-ULTRA ALWAYS need a managed switch with IGMP snooping — use NET-M4250 or NET-M4300 series
- Unmanaged switches (BG-4P1TE, NET-5DP433, NET-6RU905) are NOT suitable for NDI or AV-over-IP multicast
- For 30+ endpoints on AV-over-IP: use NET-M4300-48X-PC as core switch (10G backbone)
- Always calculate PoE budget: BG-ADAMO cameras = up to 60W each (need PoE++ 802.3bt)

**How far is the display from source?**
- <5m: HDMI direct
- 5-70m: HDBaseT Cat6 (BG-EXH-70C4)
- 70-100m: HDBaseT Cat6A (BG-EXH-100C4)
- 100-150m: HDBaseT long-range (BG-EXH-150C, 1080p only)
- >150m or 4K60 at any long distance: Fiber or AV-over-IP

**What signal does the camera output?**
- HDMI: connect directly to HDMI switcher
- 12G-SDI: connect to SDI splitter (BG-12GCSA) or SDI router, OR use SDI→HDMI converter
- NDI: connect via 1Gbps network to NDI decoder or software
- USB: connect to PC only — not compatible with AV switchers

**Need to stream online?**
- Add BG-HAVS (H.264 encoder) to HDMI output of switcher
- Or use BG-ADAMO NDI output → PC with OBS/vMix

**Need 8K?**
- Requires HDMI 2.1 throughout entire chain
- BG-8K-DA12A splitters, BG-8K-KVM21A/41A, BG-8K-AA/AD/AE converters

---

## 9. BZB GEAR PRODUCT SKU NAMING CONVENTIONS

- **BG-** prefix: all BZB Gear products
- **4K-**: HDMI 2.0 / 4K60 capable
- **8K-**: HDMI 2.1 / 8K capable
- **ADAMO**: premium PTZ camera line
- **EXH**: HDMI extender (HDBaseT)
- **EXHKVM**: HDMI+KVM extender
- **AIR**: wireless extender
- **IPGEAR**: AV-over-IP product family
- **COMMANDER**: PTZ camera controller
- **HAVS**: H.264 video streaming encoder
- **STREAM**: streaming/decoding device
- **3GS**: 3G-SDI distribution
- **12GCSA**: 12G-SDI distribution
- **MA**: matrix (e.g. 4K-88MA = 8×8 matrix)
- **VP**: video processor (multiviewer + matrix)
- **MVS**: multiviewer seamless switcher
- **VW**: video wall processor
- **DA**: distribution amplifier
- **KVM**: keyboard/video/mouse switch
- **-W / -B**: white / black color variant
- **-ND**: NDI|HX3 built-in
- **-DA**: SDI+HDMI dual output (no NDI)
- suffix numbers (12X, 25X, 31X): optical zoom factor

---

## 10. MULTI-FUNCTION PRODUCTS — ALWAYS PREFER THESE OVER SEPARATE DEVICES

⚠️ CHECK THIS TABLE FIRST before selecting individual products for each role.
One multi-function product = fewer devices, simpler setup, lower cost.

### Live Production / Streaming

| SKU | Roles covered in ONE device | Notes |
|---|---|---|
| BG-COMMANDER-ULTRA | production switcher + PTZ joystick controller + touchscreen preview | 4-ch HDMI 4K60, PoE — replaces separate switcher + separate controller |
| BG-COMMANDER-ULTRAX | production switcher + PTZ joystick controller + program monitor + confidence monitor | 4× HDMI in, 2× HDMI out (program+preview), USB-C webcam out |
| BG-COMMANDER-G2 | PTZ joystick controller + 5" NDI live preview screen (multiviewer) | See all cameras on built-in screen — replaces controller + separate multiviewer |
| BG-COMMANDER-PRO | PTZ joystick controller + HDMI preview output | HDMI out for confidence monitor |
| BG-MFVS61-G2 | production switcher + audio mixer + H.264 streaming encoder + preview output | 6-ch SDI/HDMI, built-in RTMP — replaces switcher + encoder + audio |

### When to choose:
- 3-4 cameras + need PTZ control + need switching → **BG-COMMANDER-ULTRAX** (all-in-one, 4 HDMI inputs)
- 3-6 cameras + need SDI inputs + need switching → **BG-MFVS61-G2** + **BG-COMMANDER-G2** (SDI native + NDI preview)
- Need PTZ control + want to see all cameras on one screen → **BG-COMMANDER-G2** (built-in 5" NDI screen, no extra multiviewer needed)
- Already have production switcher, just need PTZ control → **BG-COMMANDER-PRO**

### Matrix / Distribution

| SKU | Roles covered in ONE device | Notes |
|---|---|---|
| BG-4K-VP44 / VP88 / VP1616 | matrix switcher + video wall processor + multiviewer | One unit routes, scales, and creates video walls |
| BG-4K-VP44PRO | matrix switcher + multiviewer + streaming encoder | Adds H.264 stream output |
| BG-UHD-QVP-4X2 | 4×2 matrix + multiviewer | 4 sources → any combination of 2 outputs |

### Rule: if customer needs 2+ roles from the same row — use that single SKU, not separate devices.
