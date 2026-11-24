#!/usr/bin/env python3
"""Measure the focus-ring evidence and write its manifest (ledger row 95).

Reads the viewport frames and the run JSON that capture_focus_rings.sh wrote,
crops each frame around the focused control, samples the ring stroke and the
surface just outside it from the pixels, and writes manifest.json with the
measured pair plus the ratio computed from those pixels.

The point is that the number reported is read off the picture, not copied from
the stylesheet: if the ring did not paint, the sampled pixels would come back
equal to the surface and the measurement would say so.

Run with Pillow available, e.g.
  uv run --with pillow python3 measure_focus_rings.py
"""
import json
import os
import re
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
WIDTHS = (412, 768, 1440)


def luminance(rgb):
    channels = []
    for channel in rgb:
        c = channel / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def ratio(a, b):
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def hexed(rgb):
    return "#%02x%02x%02x" % rgb


def main():
    manifest = {
        "date": "2026-11-24",
        "ledger": 95,
        "method": (
            "bb browser-automation, headless Chromium, real Tab presses to reach "
            "each control, viewport screenshot at the control's rect; ring stroke "
            "and the surface outside it are sampled from the PNG, and the ratio is "
            "computed from those sampled pixels with the WCAG 2.x formula"),
        "min_contrast": 3.0,
        "captures": [],
    }
    for width in WIDTHS:
        run_path = os.path.join(HERE, f"{width}-run.json")
        if not os.path.exists(run_path):
            sys.exit(f"missing {run_path}")
        run = json.load(open(run_path, encoding="utf-8"))
        if run.get("exitCode") != 0:
            sys.exit(f"{run_path}: capture run failed: {run.get('text')}")
        for entry in json.loads(run["text"]):
            frame = entry["shot"]
            image = Image.open(frame).convert("RGB")
            scale = image.width / width
            rect = entry["rect"]
            x, y, w, h = (rect["x"] * scale, rect["y"] * scale,
                          rect["w"] * scale, rect["h"] * scale)
            # ring stroke occupies [x-5, x-2] at offset 2 + width 3. The
            # family's pill radius curves the left and right ends away from the
            # box edge, so the four mid-edge samples are the ones that always
            # land on the stroke: left/right at mid-height, top/bottom at
            # mid-width. The surface is sampled 14px further out on the same
            # four axes.
            mid_x, mid_y = int(x + w / 2), int(y + h / 2)
            ring_points = [(int(x - 4), mid_y), (int(x + w + 4), mid_y),
                           (mid_x, int(y - 4)), (mid_x, int(y + h + 4))]
            surface_points = [(int(x - 14), mid_y), (int(x + w + 14), mid_y),
                              (mid_x, int(y - 14)), (mid_x, int(y + h + 14))]
            ring_px = [image.getpixel(p) for p in ring_points
                       if 0 <= p[0] < image.width and 0 <= p[1] < image.height]
            surface_px = [image.getpixel(p) for p in surface_points
                          if 0 <= p[0] < image.width and 0 <= p[1] < image.height]
            if not ring_px or not surface_px:
                sys.exit(f"{frame}: could not sample ring/surface pixels")

            def dominant(pixels):
                counts = {}
                for pixel in pixels:
                    counts[pixel] = counts.get(pixel, 0) + 1
                return max(counts.items(), key=lambda kv: kv[1])[0]

            ring_rgb, surface_rgb = dominant(ring_px), dominant(surface_px)
            measured = ratio(ring_rgb, surface_rgb)
            crop_box = (max(0, int(x - 30)), max(0, int(y - 24)),
                        min(image.width, int(x + w + 30)),
                        min(image.height, int(y + h + 24)))
            crop_path = frame.replace(".png", "-crop.png")
            image.crop(crop_box).save(crop_path)

            entry_out = {
                "width": width,
                "page": entry["page"],
                "selector": entry["selector"],
                "control": entry["text"],
                "tab_presses": entry["presses"],
                "focused": entry["focused"],
                "computed_outline": entry["outline"],
                "computed_outline_offset": entry["outlineOffset"],
                "control_fill": entry["fill"],
                "measured_ring": hexed(ring_rgb),
                "measured_surface": hexed(surface_rgb),
                "measured_ratio": round(measured, 2),
                "passes_3_to_1": measured >= 3.0,
                "ring_samples": [hexed(p) for p in ring_px],
                "surface_samples": [hexed(p) for p in surface_px],
                "frame": os.path.basename(frame),
                "crop": os.path.basename(crop_path),
            }
            if not entry_out["focused"]:
                sys.exit(f"{frame}: the control was not the focused element")
            if not entry_out["passes_3_to_1"]:
                sys.exit(f"{frame}: measured {measured:.2f}:1, below 3:1")
            if ring_rgb == surface_rgb:
                sys.exit(f"{frame}: sampled ring equals the surface; no ring painted")
            manifest["captures"].append(entry_out)
            print(f"{width:5d} {entry['selector']:22s} ring {hexed(ring_rgb)} "
                  f"on {hexed(surface_rgb)} = {measured:.2f}:1")

    with open(os.path.join(HERE, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    print(f"manifest: {os.path.join(HERE, 'manifest.json')}")


if __name__ == "__main__":
    main()
