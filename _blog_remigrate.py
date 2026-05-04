#!/usr/bin/env python3
"""
Debbie Cooley WordPress Blog Re-Migration

Goals (per user direction):
- Keep original WordPress copy intact, do not rewrite
- Strip all WP wrapper noise (.entry-header, duplicate <h1>, stale NMLS contact block, etc.)
- Generate one Imagen 4 Fast hero image per post (Florida mortgage editorial)
- Match BLOG-TEMPLATE.md structure (.blog-post-hero, .blog-post-wrap, .blog-article, .blog-sidebar)

Phases:
  1. Build per-slug prompt map
  2. Parallel image generation (10 threads, Imagen 4 Fast → PNG → WebP + JPG)
  3. Re-fetch each WP post + clean body
  4. Emit blog/<slug>.html + update blog.html cards + sitemap
"""
import os, sys, re, json, base64, urllib.request, urllib.error, html
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, PngImagePlugin
from io import BytesIO

ROOT = Path('/Users/justinbabcock/Desktop/Websites/debbie-cooley-mortgage')
DOMAIN = "https://debbiecooleymortgage.com"
WP_BASE = "https://debbiecooleymortgage.com"

# Pull GEMINI_API_KEY from env file
ENV_KEYS = Path('/Users/justinbabcock/Desktop/Websites/.env.keys').read_text()
m = re.search(r'^GEMINI_API_KEY=(.+)$', ENV_KEYS, re.MULTILINE)
GEMINI_KEY = m.group(1).strip() if m else None
assert GEMINI_KEY, "GEMINI_API_KEY not found in .env.keys"

# ============================================================
# Posts catalog — slug, category, prompt, alt
# Same 30 we migrated before; prompts are fresh per-post
# ============================================================
POSTS = [
    # (wp_slug, new_slug, category, image_prompt, image_alt)
    ("money-for-first-time-home-buyers", "money-for-first-time-home-buyers", "First-Time Buyers",
     "editorial photograph of a young Florida couple in their late 20s receiving keys to their first home, smiling joyfully, modern suburban porch with palm trees in background, golden hour, warm natural light, photorealistic, no text, no logos",
     "Young couple receiving keys to their first home"),
    ("unlocking-dreams", "unlocking-dreams", "First-Time Buyers",
     "editorial photograph of a hand turning a key in the front door of a charming Florida bungalow, soft morning light, focus on key and door handle, warm welcoming colors, photorealistic, no text, no logos",
     "Hand unlocking the door of a Florida home"),
    ("first-time-home-buyer-loans", "first-time-home-buyer-loans-overview", "First-Time Buyers",
     "editorial photograph of a friendly Florida mortgage broker meeting with a young couple at a kitchen table, paperwork and laptop visible, bright natural light, professional but warm, photorealistic, no text, no logos",
     "Mortgage broker meeting with first-time home buyers"),
    ("a-living-legacy-how-one-new-port-richey-couple-used-a-reverse-mortgage-to-gift-their-grandchildren-25000-each-for-christmas", "living-legacy-reverse-mortgage-grandchildren", "Reverse Mortgage",
     "editorial photograph of grandparents watching grandchildren open Christmas presents in a warm Florida living room, multi-generational family scene, soft Christmas tree lights, joyful mood, photorealistic, no text, no logos",
     "Grandparents and grandchildren on Christmas morning"),
    ("helping-your-clients-help-their-parents-why-financial-planners-should-consider-reverse-mortgages", "financial-planners-should-consider-reverse-mortgages", "Reverse Mortgage",
     "editorial photograph of a financial advisor reviewing retirement plans with an older couple in a sunlit office, warm tones, paperwork and tablet on desk, professional advisory mood, photorealistic, no text, no logos",
     "Financial advisor meeting with senior clients"),
    ("take-a-second-to-breath", "take-a-second-to-breathe", "Florida Market",
     "editorial photograph of a peaceful Florida sunset over a calm bay with palm trees silhouetted, deep teal water, dusty rose sky, contemplative mood, no people, photorealistic, no text",
     "Calm Florida sunset over a bay"),
    ("understanding-the-homestead-exemption-in-florida", "florida-homestead-exemption", "Florida Market",
     "editorial photograph of a classic Florida craftsman home with a manicured lawn and palm trees, blue sky, mid-day, neighborhood mailbox in foreground, photorealistic, no text, no logos",
     "Classic Florida home with palm trees"),
    ("reverse-mortgages-for-home-healthcare-leveraging-your-home-equity", "reverse-mortgages-for-home-healthcare", "Reverse Mortgage",
     "editorial photograph of a kind in-home caregiver helping a senior woman with morning tea on a sunlit porch, warm and respectful mood, Florida home setting, photorealistic, no text, no logos",
     "Caregiver helping senior at home"),
    ("reverse-mortgage-used-for-dream-home-purchase", "reverse-mortgage-for-dream-home-purchase", "Reverse Mortgage",
     "editorial photograph of an active retired couple in their 70s standing in front of a beautiful new Florida coastal home, beachy palette, smiling, photorealistic, no text, no logos",
     "Retired couple in front of their new dream home"),
    ("why-more-financial-advisors-are-recommending-reverse-mortgages", "why-financial-advisors-recommend-reverse-mortgages", "Reverse Mortgage",
     "editorial photograph over the shoulder of a financial advisor pointing at retirement charts on a tablet while explaining to a senior couple, modern office, soft natural light, photorealistic, no text, no logos",
     "Financial advisor explaining retirement strategy"),
    ("5-ways-to-finance-generational-housing-from-traditional-mortgages-to-creative-solutions", "5-ways-to-finance-generational-housing", "Florida Market",
     "editorial photograph of three generations of a family on the porch of a multi-story Florida home, grandparents, parents, and children together, warm late-afternoon light, photorealistic, no text, no logos",
     "Multigenerational family in front of a Florida home"),
    ("demystifying-reverse-mortgages", "demystifying-reverse-mortgages", "Reverse Mortgage",
     "editorial photograph of an elderly couple at a sunlit kitchen table reviewing financial documents with a calm friendly mortgage advisor, coffee cups, paperwork, photorealistic, no text, no logos",
     "Senior couple reviewing reverse mortgage documents"),
    ("conventional-mortgage-requirements-for-condos", "conventional-mortgage-requirements-for-condos", "First-Time Buyers",
     "editorial photograph of a modern Florida coastal condo building under a clear blue sky, balconies and palm trees, mid-morning, photorealistic, no text, no logos",
     "Modern Florida coastal condo building"),
    ("how-a-reverse-mortgage-can-help-seniors-purchase-a-home", "reverse-mortgage-helps-seniors-purchase-home", "Reverse Mortgage",
     "editorial photograph of an active senior couple standing happily in front of a new ranch-style Florida home with sold sign, late afternoon golden light, photorealistic, no text, no logos",
     "Senior couple in front of their newly purchased home"),
    ("financially-preparing-for-divorce-managing-your-mortgage-and-credit-cards", "preparing-for-divorce-mortgage-credit", "Refinance & Equity",
     "editorial photograph of a thoughtful person reviewing financial documents at a kitchen table with a laptop, calm and focused mood, soft morning light, photorealistic, no text, no logos",
     "Person reviewing financial documents thoughtfully"),
    ("should-i-wait-to-buy-a-house", "should-i-wait-to-buy-a-house", "First-Time Buyers",
     "editorial photograph of a young couple sitting on outdoor steps with a notepad considering whether to buy a home, contemplative mood, golden hour Florida neighborhood, photorealistic, no text, no logos",
     "Young couple considering home purchase decision"),
    ("first-time-homebuyer", "first-time-homebuyer-guide", "First-Time Buyers",
     "editorial photograph of a smiling first-time homebuyer signing closing documents at a desk with a friendly professional across, soft natural light, paperwork and pen visible, photorealistic, no text, no logos",
     "First-time buyer signing closing documents"),
    ("guide-to-reverse-mortgage-for-children-and-their-heirs", "reverse-mortgage-guide-for-heirs", "Reverse Mortgage",
     "editorial photograph of an adult son and daughter sitting beside their elderly parents on a sunlit porch, having a warm family conversation, multi-generational, photorealistic, no text, no logos",
     "Adult children and senior parents in conversation"),
    ("debbie-cooley-guy-knows-the-trinity-reverse-mortgage-market", "trinity-reverse-mortgage-market", "Reverse Mortgage",
     "editorial photograph of a tree-lined Trinity Florida neighborhood street with manicured landscaping and Mediterranean-style homes, blue sky, photorealistic, no text, no logos",
     "Trinity Florida neighborhood"),
    ("banks-vs-mortgage-brokers-why-a-mortgage-broker-is-the-better-choice", "banks-vs-mortgage-brokers", "First-Time Buyers",
     "editorial photograph of a friendly mortgage broker shaking hands with a young couple in a warm professional office, paperwork on desk, natural light, photorealistic, no text, no logos",
     "Mortgage broker shaking hands with clients"),
    ("the-florida-hometown-heroes-housing-program", "florida-hometown-heroes-housing-program", "First-Time Buyers",
     "editorial photograph of a smiling Florida teacher, firefighter, and nurse standing together in front of a residential street, daylight, professional and proud mood, photorealistic, no text, no logos",
     "Florida hometown heroes — teacher, firefighter, and nurse"),
    ("tips-for-millennial-homebuyers", "tips-for-millennial-homebuyers", "First-Time Buyers",
     "editorial photograph of a millennial couple in their 30s with a laptop and coffee on the porch of a Florida starter home, casual and aspirational, photorealistic, no text, no logos",
     "Millennial couple researching home purchase"),
    ("self-employed-buying-a-new-home-in-2023-things-to-know", "self-employed-buying-a-home-things-to-know", "First-Time Buyers",
     "editorial photograph of a self-employed person at a home office desk with tax documents and laptop, focused and professional, natural window light, photorealistic, no text, no logos",
     "Self-employed person reviewing tax documents"),
    ("jonathan-success-story-maximizing-his-investment-portfolio-with-the-right-mortgage", "jonathan-success-investment-portfolio-mortgage", "Refinance & Equity",
     "editorial photograph of a confident professional in his 40s reviewing investment portfolio on multiple monitors in a modern home office, warm daylight, photorealistic, no text, no logos",
     "Professional reviewing investment portfolio"),
    ("improve-retirement-with-no-monthly-mortgage-payments", "improve-retirement-no-monthly-mortgage-payments", "Senior & Retirement",
     "editorial photograph of a relaxed retired couple enjoying coffee on a Florida lanai with garden view, comfortable and content mood, soft morning light, photorealistic, no text, no logos",
     "Retired couple enjoying morning coffee"),
    ("thinking-about-a-reverse-mortgage", "thinking-about-a-reverse-mortgage", "Reverse Mortgage",
     "editorial photograph of an older woman thoughtfully reading on a sunlit Florida porch with a notebook beside her, contemplative mood, warm natural light, photorealistic, no text, no logos",
     "Senior woman reading on a sunlit porch"),
    ("seniors-can-be-helped-by-reverse-mortgages", "seniors-helped-by-reverse-mortgages", "Senior & Retirement",
     "editorial photograph of a happy senior couple gardening together in their Florida backyard, healthy and active, warm natural light, photorealistic, no text, no logos",
     "Senior couple gardening together"),
    ("what-happens-to-your-social-security-when-you-lose-a-spouse", "social-security-when-you-lose-a-spouse", "Senior & Retirement",
     "editorial photograph of an older woman looking thoughtfully through a window at a peaceful garden, warm tones, gentle and respectful mood, photorealistic, no text, no logos",
     "Senior woman looking through a window"),
    ("which-homeowners-insurance-is-the-cheapest", "cheapest-homeowners-insurance", "Florida Market",
     "editorial photograph of a Florida home exterior with hurricane shutters and palm trees, blue sky, suburban neighborhood, photorealistic, no text, no logos",
     "Florida home with hurricane preparations"),
    ("closing-homebuyers", "what-to-expect-at-closing", "First-Time Buyers",
     "editorial photograph of a young couple shaking hands and smiling across a closing table with paperwork and pen, warm office, photorealistic, no text, no logos",
     "Buyers at the closing table"),
]

# Posts intentionally skipped (stale)
SKIP = [
    "should-i-wait-to-buy-a-house-2",
    "how-to-get-a-mortgage-in-2023-the-perfect-year-to-buy-a-home",
    "why-are-housing-prices-in-florida-higher-in-2022",
    "building-costs-forecasts",
    "real-estate-values-in-2022",
    "mortgage-rate-forecast",
    "construction-costs-rising",
]

# ============================================================
# Image generation
# ============================================================
IMG_DIR = ROOT / "images" / "blog"
IMG_DIR.mkdir(parents=True, exist_ok=True)

def generate_image(slug, prompt, alt):
    """Call Imagen 4 Fast and save WebP + OG JPG locally."""
    webp_path = IMG_DIR / f"{slug}.webp"
    og_path = IMG_DIR / f"{slug}-og.jpg"
    if webp_path.exists() and og_path.exists():
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
        png_bytes = base64.b64decode(data['predictions'][0]['bytesBase64Encoded'])
        # Open the PNG, optimize to WebP (1200x675) + OG JPG (1200x630)
        img = Image.open(BytesIO(png_bytes)).convert('RGB')
        img.info = {}
        # 16:9 hero crop
        img_hero = img.copy()
        img_hero.thumbnail((1200, 1200), Image.LANCZOS)
        # If aspect not 16:9, center-crop to 1200x675
        target_w, target_h = 1200, 675
        ratio = target_w / img_hero.size[0]
        new_h = int(img_hero.size[1] * ratio)
        img_hero = img_hero.resize((target_w, new_h), Image.LANCZOS)
        if new_h > target_h:
            top = (new_h - target_h) // 2
            img_hero = img_hero.crop((0, top, target_w, top + target_h))
        img_hero.info = {}
        img_hero.save(webp_path, 'WEBP', quality=78)
        # OG image — JPG, 1200x630 (Facebook prefers slightly different aspect)
        img_og = img_hero.copy()
        if img_og.size != (1200, 630):
            # crop a bit more to 1200x630
            top = (img_og.size[1] - 630) // 2 if img_og.size[1] > 630 else 0
            if img_og.size[1] > 630:
                img_og = img_og.crop((0, top, 1200, top + 630))
        img_og.info = {}
        img_og.save(og_path, 'JPEG', quality=85, optimize=True)
        return slug, "ok", None
    except Exception as e:
        return slug, "err", str(e)[:300]


def generate_all_images():
    print(f"=== Generating {len(POSTS)} hero images via Imagen 4 Fast (10 parallel)... ===")
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(generate_image, p[1], p[3], p[4]): p[1] for p in POSTS}
        ok = err = cached = 0
        for fut in as_completed(futures):
            slug, status, err_msg = fut.result()
            if status == "ok":
                ok += 1
                print(f"  ✓ {slug}")
            elif status == "cached":
                cached += 1
                print(f"  ◌ {slug} (cached)")
            else:
                err += 1
                print(f"  ✗ {slug}  ERROR: {err_msg}")
    print(f"  --- {ok} new, {cached} cached, {err} errors ---")
    return ok, cached, err


# ============================================================
# WP fetch
# ============================================================
def fetch(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'identity',
        'Connection': 'keep-alive',
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        return None


# ============================================================
# Body extraction + cleanup
# ============================================================
def extract_meta(wp_html):
    """Pull title and pubDate from WP og: + meta tags."""
    title_m = re.search(r'<meta property="og:title" content="([^"]+)"', wp_html)
    desc_m = re.search(r'<meta property="og:description" content="([^"]+)"', wp_html)
    pubdate_m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', wp_html)
    if not pubdate_m:
        pubdate_m = re.search(r'<meta property="article:published_time" content="([^"]+)"', wp_html)
    return {
        'title': html.unescape(title_m.group(1)) if title_m else "",
        'description': html.unescape(desc_m.group(1)) if desc_m else "",
        'pubdate': pubdate_m.group(1)[:10] if pubdate_m else "",
    }


def extract_body(wp_html):
    """Extract the post content from the WP page, return clean HTML."""
    # WP themes wrap content in <article class="post"> or .entry-content
    # Try several common containers
    patterns = [
        r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</div><!--\s*\.entry-content',
        r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</div>\s*</article>',
        r'<article[^>]*>(.*?)</article>',
        r'<div[^>]*class="[^"]*post-content[^"]*"[^>]*>(.*?)</div>',
    ]
    body = None
    for pat in patterns:
        m = re.search(pat, wp_html, re.DOTALL | re.IGNORECASE)
        if m:
            body = m.group(1)
            break
    if not body:
        return None
    return clean_body(body)


def clean_body(body):
    """Aggressive WP cleanup — keep copy, drop chrome."""
    # 1. Remove HTML comments
    body = re.sub(r'<!--.*?-->', '', body, flags=re.DOTALL)
    # 2. Remove any inner <h1> (we already render the title in the hero)
    body = re.sub(r'<h1[^>]*>.*?</h1>', '', body, flags=re.DOTALL | re.IGNORECASE)
    # 3. Remove inner <article> wrappers
    body = re.sub(r'</?article[^>]*>', '', body, flags=re.IGNORECASE)
    # 4. Convert <b> → <strong>
    body = re.sub(r'<b\b([^>]*)>', r'<strong\1>', body, flags=re.IGNORECASE)
    body = re.sub(r'</b>', '</strong>', body, flags=re.IGNORECASE)
    # 5. Strip wp-* / has-* classes and other noise
    def clean_attrs(m):
        tag = m.group(1)
        attrs = m.group(2) or ''
        # Drop class attrs entirely (we control styles globally)
        attrs = re.sub(r'\s+class="[^"]*"', '', attrs)
        attrs = re.sub(r"\s+class='[^']*'", '', attrs)
        # Drop id attrs (collisions, no purpose)
        attrs = re.sub(r'\s+id="[^"]*"', '', attrs)
        # Drop style attrs (we control globally)
        attrs = re.sub(r'\s+style="[^"]*"', '', attrs)
        attrs = re.sub(r"\s+style='[^']*'", '', attrs)
        # Drop data-* attrs
        attrs = re.sub(r'\s+data-[a-z0-9_-]+="[^"]*"', '', attrs)
        attrs = re.sub(r"\s+data-[a-z0-9_-]+='[^']*'", '', attrs)
        # Drop rev attribute (deprecated, used by Yoast)
        attrs = re.sub(r'\s+rev="[^"]*"', '', attrs)
        # Drop target, rel from internal links (fix later for external)
        return f'<{tag}{attrs}>'
    body = re.sub(r'<(\w+)((?:\s+[^>]*)?)/?>', clean_attrs, body)

    # 6. Strip <span> tags entirely — they wrap text-runs in WP, no semantic value
    body = re.sub(r'</?span[^>]*>', '', body, flags=re.IGNORECASE)

    # 7. Strip <div> tags entirely (let CSS handle layout)
    body = re.sub(r'</?div[^>]*>', '', body, flags=re.IGNORECASE)

    # 8. Strip the trailing author/contact block. Pattern is "Debbie Cooley Mortgage | NMLS #..."
    #    or "call Debbie Cooley Guy with Innovative Mortgage" or
    #    "Debbie Cooley Mortgage NMLS #836635" (which is a STALE, INCORRECT NMLS).
    #    Cut from any of these markers to end-of-body.
    end_markers = [
        r'<p>[^<]*Debbie Cooley Mortgage\s*\|\s*NMLS',
        r'<p>[^<]*Debbie Cooley Guy[^<]*Loan Originator',
        r'Debbie Cooley Mortgage \| NMLS #836635',  # STALE NMLS — strip on sight
        r'<p>[^<]*Equal Housing Lender[^<]*</p>',
        r'<p>[^<]*call Debbie Cooley Guy with Innovative Mortgage',
        r'<p>[^<]*Debbie Cooley\s*\|\s*Mortgage Loan Originator',
    ]
    for pat in end_markers:
        m = re.search(pat, body, re.IGNORECASE)
        if m:
            body = body[:m.start()]
            break
    # Also kill orphan tels/mailtos at the very end on their own line
    body = re.sub(r'<p>\s*\d{3}-\d{3}-\d{4}[^<]*</p>\s*$', '', body, flags=re.IGNORECASE)

    # 9. Collapse extra whitespace
    body = re.sub(r'\n{3,}', '\n\n', body)
    body = re.sub(r'<p>\s*</p>', '', body)
    body = re.sub(r'<p>\s*&nbsp;\s*</p>', '', body)
    body = re.sub(r'\s+(<br\s*/?>)', r'\1', body)

    # 10. Promote target=_blank on external links, strip from internal
    def fix_link(m):
        attrs = m.group(0)
        href_m = re.search(r'href="([^"]+)"', attrs)
        if not href_m:
            return attrs
        href = href_m.group(1)
        if href.startswith('http') and 'debbiecooleymortgage' not in href:
            # external — ensure target=_blank + rel=noopener
            if 'target=' not in attrs:
                attrs = attrs.replace('<a ', '<a target="_blank" rel="noopener" ')
        else:
            # internal — strip target/rel
            attrs = re.sub(r'\s+target="[^"]*"', '', attrs)
            attrs = re.sub(r'\s+rel="[^"]*"', '', attrs)
        return attrs
    body = re.sub(r'<a\b[^>]*>', fix_link, body)

    # 11. Strip any leftover <img> tags pointing to wp-content — replace with empty (we use the new hero)
    body = re.sub(r'<img[^>]*wp-content[^>]*/?>', '', body, flags=re.IGNORECASE)

    # 12. Clean up nested <li><h3> patterns (WP weirdness) — demote inner h3 to strong
    body = re.sub(r'<li>\s*<h3[^>]*>(.*?)</h3>', r'<li><strong>\1</strong>', body, flags=re.DOTALL | re.IGNORECASE)

    # 13. Final whitespace pass
    body = body.strip()
    return body


# ============================================================
# Page templates
# ============================================================
def build_post_page(post, body_html, related_posts, all_posts_for_meta):
    wp_slug, new_slug, category, prompt, alt = post
    meta = all_posts_for_meta[new_slug]
    title = meta['title']
    description = meta['description'][:160] if meta['description'] else f"Florida mortgage insights from Debbie Cooley, NMLS# 210817."
    pubdate = meta.get('pubdate', '2026-04-29')
    long_date = format_long_date(pubdate)
    word_count = len(re.sub(r'<[^>]+>', '', body_html).split())
    read_time = max(2, round(word_count / 220))

    canonical = f"{DOMAIN}/blog/{new_slug}/"
    hero_url = f"/images/blog/{new_slug}.webp"
    og_url = f"{DOMAIN}/images/blog/{new_slug}-og.jpg"
    alt_safe = html.escape(alt)
    title_safe = html.escape(title)
    desc_safe = html.escape(description)

    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": title,
        "description": description,
        "image": og_url,
        "datePublished": pubdate,
        "dateModified": pubdate,
        "author": {"@type": "Person", "name": "Debbie Cooley", "identifier": "NMLS# 210817"},
        "publisher": {
            "@type": "Organization",
            "name": "Debbie Cooley Mortgage",
            "logo": {"@type": "ImageObject", "url": f"{DOMAIN}/images/logo-monogram.webp"}
        },
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical}
    })

    # Related articles HTML (3 most recent in same category, exclude self)
    related_html = ""
    for r_slug, r_title in related_posts[:3]:
        related_html += f'        <a class="sidebar-link" href="/blog/{r_slug}/">{html.escape(r_title)}</a>\n'
    if not related_html:
        related_html = '        <a class="sidebar-link" href="/blog/">More from the blog →</a>'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_safe} | Debbie Cooley Mortgage</title>
<meta name="description" content="{desc_safe}">
<link rel="canonical" href="{canonical}">

<meta property="og:type" content="article">
<meta property="og:title" content="{title_safe}">
<meta property="og:description" content="{desc_safe}">
<meta property="og:image" content="{og_url}">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="Debbie Cooley Mortgage">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{og_url}">

<link rel="icon" href="/favicon.ico">
<link rel="icon" type="image/png" sizes="32x32" href="/images/favicon-32.png">
<link rel="icon" type="image/png" sizes="192x192" href="/images/favicon-192.png">
<link rel="apple-touch-icon" href="/images/apple-touch-icon.png">

<link rel="preload" as="font" type="font/woff2" href="/fonts/inter.woff2" crossorigin>
<link rel="preload" as="font" type="font/woff2" href="/fonts/playfair-display.woff2" crossorigin>
<link rel="preload" as="image" type="image/webp" href="{hero_url}" fetchpriority="high">

<link rel="stylesheet" href="/styles.css">

<!-- Google Consent Mode v2 -->
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('consent', 'default', {{
    'analytics_storage': 'granted',
    'ad_storage': 'denied',
    'ad_user_data': 'denied',
    'ad_personalization': 'denied'
  }});
</script>
<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
}})(window,document,'script','dataLayer','GTM-M267MT4');</script>
<!-- Google Analytics 4 -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-98VMJ2223D"></script>
<script>gtag('js', new Date()); gtag('config', 'G-98VMJ2223D');</script>

<script src="https://www.google.com/recaptcha/api.js?render=6Lck8aQsAAAAALMA-T6nwfkSf7bv4K-mOhkszeKh" async defer></script>
<script src="/components.js" defer></script>

<script type="application/ld+json">{schema}</script>
</head>
<body>
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-M267MT4" height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<a href="#main" class="skip-link">Skip to main content</a>

{HEADER}

<main id="main">

<section class="blog-post-hero">
  <div class="container">
    <img src="{hero_url}" alt="{alt_safe}" loading="eager" width="1200" height="675">
    <div class="blog-post-hero-content">
      <span class="blog-post-cat">{html.escape(category)}</span>
      <h1>{title_safe}</h1>
      <div class="post-meta">
        <span>Debbie Cooley</span>
        <span class="post-meta-dot"></span>
        <span>{long_date}</span>
        <span class="post-meta-dot"></span>
        <span>{read_time} min read</span>
      </div>
    </div>
  </div>
</section>

<div class="blog-post-wrap">
  <article class="blog-article">
{body_html}

    <hr style="border:0; border-top:1px solid var(--border); margin: 40px 0 28px;">
    <p style="font-size:0.9rem; color: var(--text-muted);">Have questions about your specific situation? <a href="/contact/" style="color: var(--teal);">Schedule a free consultation</a> with Debbie or call <a href="tel:7276882851" style="color: var(--teal);">727-688-2851</a>.</p>
  </article>

  <aside class="blog-sidebar">
    <div class="sidebar-card">
      <div class="sidebar-head">Related Articles</div>
      <div class="sidebar-body">
{related_html}
      </div>
    </div>
    <div class="sidebar-cta">
      <div class="sidebar-cta-title">Talk to Debbie</div>
      <p>40+ years of Florida mortgage experience. Free consultation, no high-pressure pitches.</p>
      <a href="/contact/">Get Started</a>
    </div>
    <div class="sidebar-card">
      <div class="sidebar-head">Free Resources</div>
      <div class="sidebar-body">
        <a class="sidebar-link" href="/tools/refinance-calculator/">Refinance Calculator</a>
        <a class="sidebar-link" href="/tools/reverse-mortgage-quiz/">Reverse Mortgage Quiz</a>
        <a class="sidebar-link" href="/resources/first-time-homebuyer-roadmap/">First-Time Buyer Roadmap (PDF)</a>
        <a class="sidebar-link" href="/resources/5-questions-to-ask-any-mortgage-broker/">5 Questions to Ask (PDF)</a>
      </div>
    </div>
  </aside>
</div>

</main>

{FOOTER}
</body>
</html>
'''


def format_long_date(date_str):
    """Convert YYYY-MM-DD to 'April 29, 2026'."""
    try:
        d = datetime.strptime(date_str[:10], '%Y-%m-%d')
        return d.strftime('%B %-d, %Y')
    except Exception:
        return date_str


# ============================================================
# Header / Footer (copied from main pages for consistency)
# ============================================================
sys.path.insert(0, str(ROOT))
from _build_pages import HEADER, FOOTER  # type: ignore


# ============================================================
# Main flow
# ============================================================
def main():
    # Phase 1: Generate all images
    generate_all_images()

    # Phase 2: Re-fetch + clean each post
    print(f"\n=== Re-fetching {len(POSTS)} WP posts and cleaning... ===")
    posts_meta = {}
    posts_body = {}
    for wp_slug, new_slug, category, _, _ in POSTS:
        url = f"{WP_BASE}/{wp_slug}/"
        wp_html = fetch(url)
        if not wp_html:
            print(f"  ! {wp_slug} fetch failed")
            continue
        meta = extract_meta(wp_html)
        body = extract_body(wp_html)
        if not body or len(body) < 200:
            print(f"  ! {wp_slug} body extraction returned {len(body) if body else 0} chars — skipping")
            continue
        posts_meta[new_slug] = meta
        posts_body[new_slug] = body
        print(f"  ✓ {new_slug}: {len(body.split())} words")

    # Phase 3: Build related-articles map (3 most recent same-category)
    by_cat = {}
    for wp_slug, new_slug, category, _, _ in POSTS:
        if new_slug in posts_body:
            meta = posts_meta[new_slug]
            by_cat.setdefault(category, []).append((new_slug, meta['title'], meta.get('pubdate', '2026-01-01')))
    for cat in by_cat:
        by_cat[cat].sort(key=lambda x: x[2], reverse=True)

    def related_for(new_slug, category):
        items = [(s, t) for s, t, d in by_cat.get(category, []) if s != new_slug]
        return items[:3]

    # Phase 4: Write each blog post HTML
    print(f"\n=== Writing blog post HTML files... ===")
    written = 0
    for post in POSTS:
        wp_slug, new_slug, category, prompt, alt = post
        if new_slug not in posts_body:
            print(f"  ! skipping {new_slug} — no body")
            continue
        related = related_for(new_slug, category)
        page = build_post_page(post, posts_body[new_slug], related, posts_meta)
        out = ROOT / "blog" / f"{new_slug}.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding='utf-8')
        written += 1

    print(f"  --- {written} posts written ---")

    # Phase 5: Rebuild blog index with new local hero images
    print(f"\n=== Rebuilding blog.html index ===")
    rebuild_blog_index(posts_meta, posts_body)
    print(f"  ✓ blog.html updated")

    print("\n=== DONE ===")


def rebuild_blog_index(posts_meta, posts_body):
    """Rebuild blog.html with new local images per post."""
    from _build_pages import head, write_page  # type: ignore

    # Sort posts by pubdate desc
    sorted_posts = []
    for wp_slug, new_slug, category, _, alt in POSTS:
        if new_slug not in posts_body:
            continue
        meta = posts_meta[new_slug]
        sorted_posts.append((new_slug, category, meta['title'], meta.get('pubdate', '2026-01-01'), alt))
    sorted_posts.sort(key=lambda x: x[3], reverse=True)

    # Filter buttons
    cat_counts = {}
    for _, cat, *_ in sorted_posts:
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    CATEGORIES = ["First-Time Buyers", "Reverse Mortgage", "Refinance & Equity", "Florida Market", "Senior & Retirement"]
    filter_html = '<button class="filter-btn active" data-filter="all">All ({n})</button>\n'.format(n=len(sorted_posts))
    for cat in CATEGORIES:
        n = cat_counts.get(cat, 0)
        if n > 0:
            filter_html += f'        <button class="filter-btn" data-filter="{cat}">{cat} ({n})</button>\n'

    # Cards
    cards_html = ""
    for new_slug, category, title, pubdate, alt in sorted_posts:
        try:
            d = datetime.strptime(pubdate[:10], '%Y-%m-%d')
            date_str = d.strftime('%b %-d, %Y')
        except Exception:
            date_str = pubdate
        cards_html += f'''      <a class="post-card" href="/blog/{new_slug}/" data-cat="{category}">
        <div class="post-card-thumb">
          <img src="/images/blog/{new_slug}.webp" alt="{html.escape(alt)}" loading="lazy" width="800" height="450">
        </div>
        <div class="post-card-body">
          <div class="post-card-cat">{category}</div>
          <div class="post-card-title">{html.escape(title)}</div>
          <div class="post-card-meta">{date_str}</div>
        </div>
      </a>
'''

    page_body = f'''<section class="page-hero">
  <div class="container">
    <div class="breadcrumbs"><a href="/">Home</a> <span class="sep">›</span> <span>Blog</span></div>
    <h1>Florida mortgage insights.</h1>
    <p class="lead">Articles on first-time buying, reverse mortgages, refinancing, and the Florida market — written by a 40-year licensed mortgage broker.</p>
  </div>
</section>

<section>
  <div class="container">
    <div class="blog-filters" id="blogFilters">
        {filter_html.rstrip()}
    </div>
    <div id="postGrid" class="blog-grid">
{cards_html}    </div>
  </div>
</section>

<script>
document.querySelectorAll('#blogFilters .filter-btn').forEach((btn) => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('#blogFilters .filter-btn').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    const filter = btn.getAttribute('data-filter');
    document.querySelectorAll('#postGrid .post-card').forEach((card) => {{
      const cat = card.getAttribute('data-cat');
      card.style.display = (filter === 'all' || cat === filter) ? '' : 'none';
    }});
  }});
}});
</script>
'''

    write_page("blog.html", page_body,
        "Florida Mortgage Insights — Blog | Debbie Cooley Mortgage",
        "Articles on first-time buying, reverse mortgages, refinancing, and the Florida market — by a 40-year licensed Florida mortgage broker.",
        "/blog/")


if __name__ == "__main__":
    main()
