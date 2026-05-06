#!/usr/bin/env python3
"""
Generate Florida + brand-matched hero images for loan-program and resource pages.

Voice: warm, editorial, Floridian. Brand colors: deep teal (#2C605E), dusty rose
(#C28A7A), cream. Architectural cues: white siding + navy shutters, Mediterranean
revival, craftsman bungalows. Lighting: warm golden-hour, soft morning light.
"""
import os, sys, re, json, base64, urllib.request, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from io import BytesIO

ROOT = Path('/Users/justinbabcock/Desktop/Websites/debbie-cooley-mortgage')
ENV = (ROOT.parent / '.env.keys').read_text()
GEMINI_KEY = re.search(r'^GEMINI_API_KEY=(.+)$', ENV, re.MULTILINE).group(1).strip()

IMG_DIR = ROOT / 'images' / 'pages'
IMG_DIR.mkdir(parents=True, exist_ok=True)

# Common style fragment used on every prompt
BRAND = ("editorial mortgage-broker website hero photograph. Warm golden-hour or "
         "soft morning light. Subtle teal and dusty-rose color accents in wardrobe "
         "or setting. Florida-specific feel: palm trees or palm fronds in soft focus, "
         "white siding with navy shutters or Mediterranean tile, lush green landscaping, "
         "blue Florida sky. Photorealistic, professional, friendly mood, "
         "no text, no logos, no watermarks, no signage.")

PAGES = [
    # (slug, prompt, alt)
    ("loan-programs",
     f"A wide editorial scene of a happy multi-generational Florida family in front of a beautiful craftsman-style home with white siding, navy blue shutters, and palm trees. Multiple ages — young couple, parents, retired grandparents. Warm welcoming atmosphere. {BRAND}",
     "Multi-generational Florida family in front of a craftsman home"),

    ("conventional-loans",
     f"Editorial photograph of a young Florida couple in their early 30s standing on the front porch of a charming traditional Florida home with manicured landscaping, palm trees, and a Florida-blue sky. The home has white clapboard siding and a wraparound porch. {BRAND}",
     "Young couple on the porch of their conventional Florida home"),

    ("fha-loans",
     f"Editorial photograph of a Florida first-time-buyer family — young couple with a small child — proudly standing in front of a modest but charming starter home in a Florida neighborhood. Affordable and welcoming feel, fresh new beginnings. Palm trees, light pastel home exterior. {BRAND}",
     "First-time-buyer family in front of a modest Florida starter home"),

    ("va-loans",
     f"Editorial photograph of a respectful, dignified Florida military couple in their 30s in front of a lovely Florida home. The man may be a veteran in subtle civilian attire, the woman a service member or vice versa, with a small American flag visible somewhere in the porch decor. Honor and pride without being heavy-handed. Palm trees, blue sky. {BRAND}",
     "Florida veteran couple in front of their home"),

    ("first-time-buyer",
     f"Editorial photograph of an excited young couple holding a brand-new house key together, smiling, in front of their first Florida home. Sun-drenched, hopeful, milestone-moment feel. Palm trees and Florida greenery in the background. The couple is in their late 20s, casual but stylish. {BRAND}",
     "First-time buyers holding the key to their new Florida home"),

    ("reverse-mortgage",
     f"Editorial photograph of an active, vibrant retired couple in their 70s relaxing on the lanai of a beautiful Florida home with screen enclosure and tropical plants. They are reading or having coffee, exuding contentment and financial peace. Wicker furniture, soft cushions in dusty-rose tones. {BRAND}",
     "Active retired couple enjoying their Florida lanai"),

    ("refinance",
     f"Editorial photograph of a Florida couple in their 40s sitting at a sunlit kitchen island with a laptop and a cup of coffee, reviewing financial paperwork together. Light wood cabinets, large window with palm fronds visible outside. Calm, focused, smart-financial-decision mood. {BRAND}",
     "Couple reviewing refinance options at a sunlit Florida kitchen"),

    ("areas-served",
     f"Wide editorial Florida coastal scene with the Tampa Bay region in soft focus — a single-family neighborhood in the foreground (Spanish-tile rooflines, palm trees), the bay or Gulf water visible in the distance, golden hour. Captures the variety of Florida west-coast living. {BRAND}",
     "Florida Tampa Bay neighborhood at golden hour"),

    ("about",
     f"Editorial photograph of an inviting Florida home office or living-room setup — soft armchair, a notebook on a side table, large window with palm fronds and natural light, plants, calm welcoming professional atmosphere. No people. Inviting space for a financial conversation. {BRAND}",
     "Inviting Florida home office for a mortgage consultation"),

    ("contact",
     f"Editorial photograph of a friendly Florida mortgage broker (a woman in her 60s with short blond hair and stylish glasses) shaking hands with clients across a sunlit table. Warm, welcoming consultation moment. Palm fronds visible through a window. {BRAND}",
     "Florida mortgage broker shaking hands with clients"),

    # Resource / tool hubs
    ("resources",
     f"Editorial photograph of an open notebook, a calculator, and a cup of coffee on a beautiful sunlit wooden table with a small potted palm. Casual planning vibe, organized and approachable. Soft dusty-rose linen and teal mug accents. {BRAND}",
     "Notebook, calculator, and coffee on a sunlit table"),

    ("refinance-calculator",
     f"Editorial photograph of someone's hands on a laptop on a sunlit Florida lanai or porch table, with a coffee cup and small plant, focusing on financial planning. Tasteful, calm, focused. No screen content visible. {BRAND}",
     "Hands working on a laptop at a Florida porch table"),

    ("reverse-mortgage-quiz",
     f"Editorial photograph of a thoughtful older Florida woman in her 70s sitting in a sunny garden chair with a notepad on her lap, looking off contemplatively at lush tropical plants. Reflective, peaceful, no rush. Warm light, dusty-rose top. {BRAND}",
     "Senior woman thoughtfully reflecting in a Florida garden"),

    ("first-time-homebuyer-roadmap",
     f"Editorial photograph of a young Florida couple looking at a paper map or checklist together at a sunlit kitchen island, planning their home-buying journey. Hopeful and organized vibe. Palm fronds in soft focus through a window. {BRAND}",
     "Young couple planning their home-buying roadmap"),

    ("5-questions-to-ask-any-mortgage-broker",
     f"Editorial photograph of a couple sitting across from a friendly Florida mortgage broker, leaning in attentively as the broker explains something with hand gestures. Trust-building, real-conversation moment. Warm light through tall windows with palm fronds. {BRAND}",
     "Couple meeting attentively with a mortgage broker"),

    ("refinancing-during-divorce",
     f"Editorial photograph of someone (back of head only, no face shown) sitting alone at a sunlit kitchen table with a notebook, organizing paperwork. Calm, contemplative, dignified. Soft warm morning light, plants, dusty-rose color in scarf or cushion. {BRAND}",
     "Person organizing paperwork at a sunlit Florida kitchen table"),
]


def gen(slug, prompt):
    webp = IMG_DIR / f"{slug}.webp"
    og = IMG_DIR / f"{slug}-og.jpg"
    if webp.exists() and og.exists():
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
        if 'predictions' not in data or not data['predictions']:
            return slug, "err", str(data)[:300]
        png = base64.b64decode(data['predictions'][0]['bytesBase64Encoded'])
        img = Image.open(BytesIO(png)).convert('RGB')
        img.info = {}
        # WebP hero @ 1600×900 max for retina
        h = img.copy()
        h.thumbnail((1600, 1600), Image.LANCZOS)
        target_w, target_h = 1600, 900
        ratio = target_w / h.size[0]
        new_h = int(h.size[1] * ratio)
        h = h.resize((target_w, new_h), Image.LANCZOS)
        if new_h > target_h:
            top = (new_h - target_h) // 2
            h = h.crop((0, top, target_w, top + target_h))
        h.info = {}
        h.save(webp, 'WEBP', quality=78)
        # OG JPG @ 1200×630
        o = img.copy()
        o.thumbnail((1200, 1200), Image.LANCZOS)
        ratio = 1200 / o.size[0]
        new_h = int(o.size[1] * ratio)
        o = o.resize((1200, new_h), Image.LANCZOS)
        if new_h > 630:
            top = (new_h - 630) // 2
            o = o.crop((0, top, 1200, top + 630))
        o.info = {}
        o.save(og, 'JPEG', quality=85, optimize=True)
        return slug, "ok", None
    except Exception as e:
        return slug, "err", str(e)[:300]


print(f"=== Generating {len(PAGES)} page hero images via Imagen 4 Fast (10 parallel)... ===")
with ThreadPoolExecutor(max_workers=10) as ex:
    futures = {ex.submit(gen, p[0], p[1]): p[0] for p in PAGES}
    ok = err = cached = errors = []
    ok = err = cached = 0
    error_slugs = []
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
            error_slugs.append(slug)
            print(f"  ✗ {slug}: {msg}")
    print(f"\n--- {ok} new, {cached} cached, {err} errors ---")

# Retry errors serially
if error_slugs:
    print(f"\n=== Retrying {len(error_slugs)} serially with delay... ===")
    for slug in error_slugs:
        prompt = next(p[1] for p in PAGES if p[0] == slug)
        s, status, msg = gen(slug, prompt)
        if status == "ok":
            print(f"  ✓ {s}")
        else:
            print(f"  ✗ {s}: {msg}")
        time.sleep(2)

# Save the alt-text map for the HTML updater
ALT_MAP = {p[0]: p[2] for p in PAGES}
(ROOT / '_page_heroes_alt.json').write_text(json.dumps(ALT_MAP, indent=2))
print(f"\nAlt-text map written to _page_heroes_alt.json")
