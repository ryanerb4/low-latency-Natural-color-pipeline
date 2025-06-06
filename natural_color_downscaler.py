#!/usr/bin/env python3
"""natural_color_downscaler.py

Fully runnable script that searches Microsoft Planetary Computer STAC for Sentinel‑2
(preferred) and Landsat 8/9 imagery, filters by cloud cover, applies pixel‑level
cloud masks, optionally pan‑sharpens Landsat to 15 m, and exports:

  • Cloud‑Optimized GeoTIFF (default) **and/or**
  • WebP preview (RGB, 8‑bit) when `--webp` is specified.

Requirements:
  pystac-client, planetary-computer, rioxarray, rasterio, xarray, numpy,
  shapely, pillow, tqdm.

SAS token: set env var `PC_SAS_TOKEN` or pass `--token`.
"""
from __future__ import annotations
import argparse, datetime as dt, os, pathlib, json, sys, tempfile
import numpy as np
import xarray as xr
import rioxarray as rxr
import rasterio
from rasterio.enums import Resampling
from shapely.geometry import shape, mapping
from shapely import wkt
from pystac_client import Client
import planetary_computer as pc
from PIL import Image
from tqdm import tqdm

###############################################################################
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--aoi", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--out", required=True)

    p.add_argument("--max-cloud", type=float, default=20)
    p.add_argument("--pansharpen", action="store_true")
    p.add_argument("--webp", action="store_true",
                   help="Also write a WebP preview alongside the COG")
    p.add_argument("--token", help="Planetary Computer SAS token")
    return p.parse_args()

###############################################################################
def load_geom(spec):
    spec = spec.strip()
    if spec.startswith("{"):
        return shape(json.loads(spec))
    p = pathlib.Path(spec)
    if p.exists():
        import fiona
        with fiona.open(p) as src:
            return shape(next(iter(src)))
    return wkt.loads(spec)

###############################################################################
def stac_search(geom, end_date, token):
    client = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    end_dt = dt.datetime.fromisoformat(end_date)
    start_dt = end_dt - dt.timedelta(days=14)
    def _q(coll):
        return list(client.search(collections=[coll],
                                  intersects=mapping(geom),
                                  datetime=f"{start_dt.date()}/{end_dt.date()}",
                                  sortby=[{"field":"datetime","direction":"desc"}],
                                  max_items=40).items())
    items = _q("sentinel-2-l2a") + _q("landsat-c2-l2")
    return [pc.sign(it, token=token) for it in items]

###############################################################################
def load_cloud_mask(item, sensor, geom):
    if sensor == "Sentinel-2":
        href = item.assets["SCL"].href
        da = rxr.open_rasterio(href, masked=True, chunks={"band":1})
        cloudy = da.isin([8,9,10,11])
    else:
        href = item.assets["QA_PIXEL"].href
        da = rxr.open_rasterio(href, masked=True, chunks={"band":1})
        cloudy = da != 0
    cloudy = cloudy.rio.clip([mapping(geom)], cloudy.rio.crs, drop=True)
    return cloudy

###############################################################################
def cloud_pct(mask):
    return float(mask.mean().compute())*100.0

###############################################################################
def get_rgb(item, sensor, geom, pansharpen):
    if sensor == "Sentinel-2":
        keys = ["B04","B03","B02"]  # 10 m
    else:
        keys = ["red","green","blue"]
    layers=[]
    for k in keys:
        da = rxr.open_rasterio(item.assets[k].href, masked=True, chunks={"band":1})
        da = da.rio.clip([mapping(geom)], da.rio.crs, drop=True)
        layers.append(da)
    rgb = xr.concat(layers, dim="band")
    if sensor.startswith("Landsat") and pansharpen:
        pan = rxr.open_rasterio(item.assets["pan"].href, masked=True, chunks={"band":1})
        pan = pan.rio.clip([mapping(geom)], pan.rio.crs, drop=True)
        rgb = brovey(rgb, pan)
    return rgb

def brovey(rgb, pan):
    sum_rgb = rgb.sum(dim="band")
    ratio = xr.where(sum_rgb==0, 0, pan/sum_rgb)
    return rgb * ratio

###############################################################################
def save_cog(rgb, path):
    rgb.rio.to_raster(path, driver="COG", compress="DEFLATE", dtype="float32")

def save_webp(rgb, path):
    # Convert to 0‑255 uint8, ignoring NaNs
    arr = rgb.compute().astype("float32").values
    nan_mask = np.isnan(arr)
    arr[nan_mask] = 0
    arr_min, arr_max = np.nanpercentile(arr, (2, 98))
    arr = np.clip((arr - arr_min)/(arr_max-arr_min+1e-6)*255, 0, 255).astype("uint8")
    img = np.transpose(arr, (1,2,0))  # band,y,x -> y,x,band
    Image.fromarray(img).save(path, format="WEBP", quality=90)

###############################################################################
def main():
    args = parse_args()
    token = args.token or os.getenv("PC_SAS_TOKEN")
    if not token:
        sys.exit("Planetary Computer SAS token required (env PC_SAS_TOKEN or --token).")
    geom = load_geom(args.aoi)
    items = stac_search(geom, args.date, token)

    selected=None
    for it in items:
        sensor = "Sentinel-2" if it.collection_id.startswith("sentinel-2") else f"Landsat-{it.properties.get('platform','')}"
        if it.properties.get("eo:cloud_cover",100) > args.max_cloud:
            continue
        mask = load_cloud_mask(it, sensor, geom)
        if cloud_pct(mask) > args.max_cloud:
            continue
        selected=(it,sensor,mask); break
    if not selected:
        sys.exit("No scene meets cloud criteria.")
    item,sensor,mask = selected
    rgb = get_rgb(item,sensor,geom,args.pansharpen)
    # Apply mask
    rgb = xr.where(mask, np.nan, rgb)

    out_path = pathlib.Path(args.out).expanduser()
    save_cog(rgb, out_path)
    print("✓ COG saved to", out_path)

    if args.webp:
        webp_path = out_path.with_suffix(".webp")
        save_webp(rgb, webp_path)
        print("✓ WebP preview saved to", webp_path)

if __name__ == "__main__":
    main()
