# Natural‑Color Downscaler 🌍

A one‑stop CLI to grab the **newest, cloud‑filtered natural‑color image** (RGB) over any AOI on or before a target date — using the free **Sentinel‑2 L2A** (10 m) feed from ESA or, when that is unavailable/too cloudy, **Landsat 8/9 Collection‑2 L2** (30 m, optional 15 m pan‑sharpen) from NASA/USGS.

Outputs:

* **Cloud‑Optimized GeoTIFF (COG)** — masked, float32 RGB
* **WebP preview** (optional `--webp`) — lightweight 8‑bit RGB for dashboards

---

## 🔑 Authentication

The script queries the **Microsoft Planetary Computer** STAC API, which requires a SAS token.  
Create a (free) token at <https://planetarycomputer.microsoft.com/account> and provide it via:

```bash
export PC_SAS_TOKEN="sv=2023‑05‑30&ss=bfqt&srt=co&sp=rl&se=2025‑07‑07T16:00:00Z&sig=..."
```

—or— pass it with `--token`.

---

## ⚡ Quick‑start

```bash
# 1.  Install deps (venv or conda recommended)
pip install -r requirements_natural.txt

# 2.  Download latest clear RGB over Jordanelle Reservoir, Utah
python natural_color_downscaler.py   --aoi "POINT (-111.152 40.684)"   --date 2025-06-07   --max-cloud 15   --pansharpen   --webp   --out jordanelle_rgb.tif
```

Result:

```
jordanelle_rgb.tif   # 3‑band 32‑bit COG (masked)
jordanelle_rgb.webp  # 8‑bit preview (≈200 KB)
```

---

## 🛠️ CLI reference

| Flag | Default | Description |
|------|---------|-------------|
| `--aoi` | — | AOI polygon (WKT, GeoJSON string, or vector file) |
| `--date` | — | Target date (`YYYY‑MM‑DD`). Script selects newest scene ≤ date |
| `--out` | — | Output COG path (`.tif`). WebP uses same basename |
| `--max-cloud` | **20** | Reject scenes with cloud % above threshold (both STAC & pixel masks) |
| `--pansharpen` | off | Brovey pan‑sharpen Landsat to 15 m |
| `--webp` | off | Save a WebP preview (`.webp`) alongside COG |
| `--token` | `$PC_SAS_TOKEN` | Planetary Computer SAS token override |

---

## 🧩 How it works

1. **STAC query** – Searches Sentinel‑2 first, then Landsat, sorted by timestamp desc.  
2. **Scene cloud filter** – Uses `eo:cloud_cover` metadata and pixel‑level masks:  
   * Sentinel‑2 SCL classes 8‑11 → cloud  
   * Landsat QA_PIXEL cloud bit ≠ 0  
3. **RGB stack** – Downloads 10 m (S2) or 30 m (Landsat) R,G,B COGs.  
4. **Pan‑sharpen** (optional) – Brovey transform with Landsat 15 m panchromatic band.  
5. **Export** – Writes masked COG + optional WebP (histogram‑stretched 8‑bit).  

---

## 📦 Requirements

See `requirements_natural.txt`.

Core: `pystac-client`, `planetary-computer`, `rioxarray`, `xarray`, `rasterio`, `numpy`, `shapely`, `pillow`, `tqdm`.

GPU **not** required.

---

*Created for rapid, high‑quality natural‑color basemaps for small lakes & wetlands — © 2025*
