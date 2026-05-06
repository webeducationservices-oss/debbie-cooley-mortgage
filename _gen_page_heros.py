#!/usr/bin/env python3
"""Generate Florida-feel hero images for loan program + resource pages via Imagen 4 Fast."""
import os, sys, re, json, base64, urllib.request, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from io import BytesIO

ROOT = Path('/Users/justinbabcock/Desktop/Websites/debbie-cooley-mortgage')
ENV = Path('/Users/justinbabcock/Desktop/Websites/.env.keys').read_text()
GEMINI_KEY = re.search(r'^GEMINI_API_KEY=(.+)$', ENV, re.MULTILINE).group(1).strip()

# Output dir
OUT = ROOT / "images" / "page-heros"
OUT.mkdir(parents=True, exist_ok=True)

# All shots have this prefix appended for brand consistency
STYLE = (
    "warm natural light, cream and teal color palette, dusty rose accents, "
    "Florida tropical setting, hopeful and reassuring mood, photorealistic, "
    "no text overlays, no signage, no brand logos, editorial magazine photography"
)

PAGES = [
    # (slug, prompt, alt)
    ("loan-programs",
     "establishing photograph of a charming Florida Mediterranean-style home with terracotta tile roof and white stucco walls, palm trees and a manicured front lawn, bright morning sky, no people, " + STYLE,
     "Florida Mediterranean-style home with palm trees"),

    ("conventional-loans",
     "young Florida couple in their early 30s standing on the front porch of a charming craftsman bungalow, holding hands and smiling at each other, late afternoon golden light, palm tree visible in background, " + STYLE,
     "Couple on front porch of their conventional-financed Florida home"),

    ("fha-loans",
     "first-time-homebuyer family — young couple holding a small child on the steps of a modest pastel-colored Florida cottage, blue sky, fresh-mowed lawn, hopeful moment, " + STYLE,
     "Young family in front of their first home"),

    ("va-loans",
     "U.S. military veteran couple — woman in her 30s holding house keys, husband in casual veteran cap with American flag pin, standing proudly outside a Florida ranch home with American flag on the porch, warm afternoon light, " + STYLE,
     "Veteran couple receiving keys to their VA-financed Florida home"),

    ("first-time-buyer",
     "young Florida couple in their late 20s walking hand-in-hand up the driveway of their first home with a SOLD real-estate sign in the foreground (sign blurred, no readable text), palm tree, golden hour, hopeful, " + STYLE,
     "First-time buyers walking up to their new home"),

    ("reverse-mortgage",
     "content elderly Florida couple in their 70s sitting together on a screened lanai with a garden view, morning coffee mugs in hand, soft golden light, peaceful and dignified mood, " + STYLE,
     "Senior couple on their lanai enjoying retirement"),

    ("refinance",
     "homeowner — woman in her 40s — reviewing financial paperwork at a sunlit kitchen table with a calculator, laptop, and coffee, soft window light, focused but content mood, plant visible, " + STYLE,
     "Homeowner reviewing refinance paperwork at her kitchen table"),

    ("resources",
     "clean modern Florida desk setup — laptop, notebook, terracotta succulent pot, mug of coffee, sun streaming in through a window with palm tree silhouette outside, no people, top-down or three-quarter angle, " + STYLE,
     "Clean Florida desk setup with laptop and coffee"),

    ("refinance-calculator",
     "close-up of hands using a calculator next to a mortgage statement on a warm wooden desk, soft directional natural light, ring on hand visible, no faces, focused composition, " + STYLE,
     "Hands using a calculator with mortgage paperwork"),

    ("reverse-mortgage-quiz",
     "Florida senior woman in her late 60s thoughtfully looking at a tablet on her sunlit lanai, palm tree visible through the screen mesh, contemplative and dignified, " + STYLE,
     "Senior woman thoughtfully reviewing information on a tablet"),

    ("first-time-homebuyer-roadmap",
     "young couple looking at a printed real-estate guidebook together at a coffee shop table, two coffees in front of them, hopeful and excited, Florida sunlight through window, " + STYLE,
     "Young couple reviewing a homebuyer guide together"),

    ("5-questions-to-ask-any-mortgage-broker",
     "thoughtful woman in her 30s writing in a notebook at a sunlit dining table with mortgage paperwork in front of her, plant in background, Florida home interior, focused but warm mood, " + STYLE,
     "Woman writing notes about questions to ask a mortgage broker"),
]


def gen(slug, prompt, alt):
    webp = OUT / f"{slug}.webp"
    og_jpg = OUT / f"{slug}-og.jpg"
    if webp.exists() and og_jpg.exists():
        return slug, "cached", None

    body = json.dumps({
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": "16:9"}
    }).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-fast-generate-001:predict?key={GEMINI_KEY}",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        if "predictions" not in data or not data["predictions"]:
            return slug, "err", str(data)[:300]
        png = base64.b64decode(data["predictions"][0]["bytesBase64Encoded"])
        img = Image.open(BytesIO(png)).convert("RGB")
        img.info = {}
        # 16:9 hero — 1280x720 max
        img.thumbnail((1280, 1280), Image.LANCZOS)
        # center-crop to 16:9 if not already
        target_w, target_h = 1280, 720
        ratio = target_w / img.size[0]
        new_h = int(img.size[1] * ratio)
        img = img.resize((target_w, new_h), Image.LANCZOS)
        if new_h > target_h:
            top = (new_h - target_h) // 2
            img = img.crop((0, top, target_w, top + target_h))
        img.info = {}
        img.save(webp, "WEBP", quality=78)
        # OG variant — slightly different aspect 1200x630, JPEG
        og = img.copy()
        if og.size[1] > 630:
            top = (og.size[1] - 630) // 2
            og = og.crop((0, top, og.size[0], top + 630))
        og.thumbnail((1200, 1200), Image.LANCZOS)
        og.info = {}
        og.save(og_jpg, "JPEG", quality=85, optimize=True)
        return slug, "ok", None
    except Exception as e:
        return slug, "err", str(e)[:300]


def main():
    print(f"=== Generating {len(PAGES)} page heros via Imagen 4 Fast (8 parallel) ===")
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(gen, *p): p[0] for p in PAGES}
        ok = err = cached = 0
        for fut in as_completed(futures):
            slug, status, msg = fut.result()
            if status == "ok":
                ok += 1
                print(f"  ✓ {slug}")
            elif status == "cached":
                cached += 1
                print(f"  ◌ {slug} (cached)")
            else:
                err += 1
                print(f"  ✗ {slug}: {msg}")
    print(f"  --- {ok} new, {cached} cached, {err} errors ---")

    # Serial retry for any that errored (rate limiting)
    if err:
        print("\nRetrying errored ones serially...")
        time.sleep(3)
        for p in PAGES:
            if not (OUT / f"{p[0]}.webp").exists():
                slug, status, msg = gen(*p)
                if status == "ok":
                    print(f"  ✓ {slug}")
                else:
                    print(f"  ✗ {slug}: {msg}")
                time.sleep(2)


if __name__ == "__main__":
    main()
