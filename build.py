#!/usr/bin/env python3
"""
Build the Polarity of Grief companion site.

Input   content/moments.csv          the single source of truth
        public/media/manifest.json   written by process_media.py
        assets/site.css

Output  public/index.html            the home page
        public/chapters/index.html   every part and chapter
        public/c/<n>-<slug>/         one page per chapter
        public/m/<id>/               one page per moment  <- what the QR codes open
        public/moments/index.html    a flat index of every moment
        public/404.html

Moment URLs are the contract with the printed book: once a code is printed,
/m/w014/ must keep working forever. Nothing else in this file is permanent.
"""

import csv
import html
import json
import os
import re
import shutil
import sys
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(HERE, "public")
MOMENTS_CSV = os.path.join(HERE, "content", "moments.csv")
MANIFEST = os.path.join(PUBLIC, "media", "manifest.json")

# Where the site lives on its host, as a path from the domain root.
#
# On a domain of its own — polarityofgrief.com, or a Cloudflare Pages URL —
# this is "/" and the printed codes read /m/w014/, which is what they should
# read forever.
#
# GitHub Pages is the exception. A project site is served from a folder named
# after the repository, so the same moment is at /polarity-of-grief/m/w014/.
# Set BASE_PATH to match, or the 404 page and every permanent address printed
# on the site will point at the domain root and miss:
#
#     BASE_PATH=/polarity-of-grief/ python3 build.py
#
# The day a real domain is attached, drop the variable and rebuild.
BASE = os.environ.get("BASE_PATH", "/")
if not BASE.startswith("/"):
    BASE = "/" + BASE
if not BASE.endswith("/"):
    BASE += "/"

SITE_NAME = "Polarity of Grief"
TAGLINE = "The companion to Rob McFadden's book about his son Walker."
WALKER = "Anthon Walker McFadden"
DATES = "25 July 2005 &ndash; 5 March 2022"

PART_NAMES = OrderedDict([
    ("One", "HIM"),
    ("Two", "THE HOUSE WE WERE BUILDING"),
    ("Three", "AFTER"),
    ("Four", "MOVING FORWARD"),
])
PART_NUMERAL = {"One": "I", "Two": "II", "Three": "III", "Four": "IV"}

e = html.escape


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)


def depth_prefix(depth):
    return "../" * depth if depth else ""


# ---------------------------------------------------------------- templates

def page(title, body, depth=0, description="", hero_canvas=False, extra="",
         absolute=False):
    # The 404 is served from whatever address the visitor mistyped, so its own
    # links have to be absolute — a relative path would resolve against a
    # directory that does not exist.
    up = BASE if absolute else depth_prefix(depth)
    full_title = title if title == SITE_NAME else f"{title} &middot; {SITE_NAME}"
    canvas_js = RIVER_JS if hero_canvas else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{full_title}</title>
<meta name="description" content="{e(description or TAGLINE)}">
<meta property="og:title" content="{full_title}">
<meta property="og:description" content="{e(description or TAGLINE)}">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bodoni+Moda:opsz,ital,wght@6..96,0,400;6..96,0,500;6..96,1,400&family=Libre+Franklin:wght@300;400;500;600&display=swap">
<link rel="stylesheet" href="{up}assets/site.css">
{extra}
</head>
<body>

<div class="wrap">
<nav>
  <a class="brand serif" href="{up or './'}">Polarity of Grief</a>
  <ul>
    <li><a href="{up}chapters/">Chapters</a></li>
    <li><a href="{up}moments/">Every moment</a></li>
    <li><a href="{up}#reading">Reading with the book</a></li>
  </ul>
</nav>
</div>

{body}

<div class="wrap"><footer>
  <span>{SITE_NAME} &middot; Rob McFadden</span>
  <span>{WALKER} &middot; {DATES}</span>
</footer></div>
{canvas_js}
</body>
</html>
"""


RIVER_JS = """
<script>
(function(){
  var c=document.getElementById('river');if(!c)return;
  var ctx=c.getContext('2d'),w,h,t=0,lines=28;
  function size(){var d=window.devicePixelRatio||1;w=c.width=c.offsetWidth*d;h=c.height=c.offsetHeight*d;}
  size();addEventListener('resize',size);
  var reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  function draw(){
    var d=window.devicePixelRatio||1;
    ctx.clearRect(0,0,w,h);
    for(var i=0;i<lines;i++){
      var y0=h*(0.15+0.75*i/lines);
      ctx.beginPath();
      for(var x=0;x<=w;x+=12*d){
        var y=y0+Math.sin(x/(260*d)+t*0.6+i*0.35)*18*d+Math.sin(x/(90*d)-t*0.4+i)*5*d;
        x===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
      }
      var a=0.05+0.12*Math.abs(Math.sin(i*0.7+t*0.3));
      ctx.strokeStyle='rgba(127,179,200,'+a+')';ctx.lineWidth=1*d;ctx.stroke();
    }
    t+=0.008;if(!reduce)requestAnimationFrame(draw);
  }
  draw();
})();
</script>
"""


# ---------------------------------------------------------------- media bits

def media_block(entries, depth, moment_title):
    """The media for a moment page: video player first, then a photo grid."""
    if not entries:
        return ('<div class="no-media"><p>The photographs for this moment are '
                'still being gathered.</p></div>')
    up = depth_prefix(depth)
    out = []
    videos = [m for m in entries if m["type"] == "video"]
    images = [m for m in entries if m["type"] == "image"]

    for v in videos:
        runtime = f'<span class="rt">{v["runtime"]}</span>' if v.get("runtime") else ""
        out.append(
            f'<figure class="player">'
            f'<video controls preload="metadata" playsinline '
            f'poster="{up}{v["poster"]}">'
            f'<source src="{up}{v["src"]}" type="video/mp4">'
            f'Your browser cannot play this video. '
            f'<a href="{up}{v["src"]}">Download it instead.</a>'
            f'</video>{runtime}</figure>')

    if images:
        cls = "gallery one" if len(images) == 1 else "gallery"
        cells = []
        for i, im in enumerate(images, 1):
            alt = e(f"{moment_title} — photograph {i}") if len(images) > 1 else e(moment_title)
            dims = ' width="%s" height="%s"' % (im["w"], im["h"]) if im.get("w") else ""
            cells.append(
                f'<a class="shot" href="{up}{im["src"]}">'
                f'<img loading="lazy" src="{up}{im["thumb"]}" alt="{alt}"{dims}>'
                f'</a>')
        out.append(f'<div class="{cls}">' + "".join(cells) + "</div>")
    return "\n".join(out)


def thumb_for(entries, up):
    """A single representative image for listings."""
    if not entries:
        return None
    for m in entries:
        if m["type"] == "image":
            return up + m["thumb"]
    for m in entries:
        if m["type"] == "video":
            return up + m["poster"]
    return None


# ---------------------------------------------------------------- pages

def build_home(moments, media, stats):
    featured = next((m for m in moments if m["id"] == "w010"), None) \
        or next((m for m in moments if media.get(m["id"])), moments[0])
    fm = media.get(featured["id"], [])
    fvid = next((x for x in fm if x["type"] == "video"), None)

    if fvid:
        feature_media = (
            f'<video controls preload="metadata" playsinline '
            f'poster="{fvid["poster"]}"><source src="{fvid["src"]}" '
            f'type="video/mp4"></video>')
    else:
        first = thumb_for(fm, "")
        feature_media = f'<img src="{first}" alt="{e(featured["title"])}">' if first else ""

    strip = []
    for m in moments:
        if len(strip) >= 4:
            break
        if m["id"] == featured["id"]:
            continue
        t = thumb_for(media.get(m["id"], []), "")
        if t:
            strip.append(
                f'<a class="cell" href="m/{m["id"]}/" data-l="{e(m["title"][:28])}">'
                f'<img loading="lazy" src="{t}" alt="{e(m["title"])}"></a>')

    # parts as the river's four stops
    part_cards = []
    for pk, pname in PART_NAMES.items():
        rows = [m for m in moments if m["part"] == pk]
        if not rows:
            continue
        chapters = OrderedDict()
        for m in rows:
            chapters.setdefault(m["chapter_title"], None)
        pic = None
        for m in rows:
            pic = thumb_for(media.get(m["id"], []), "")
            if pic:
                break
        img = f'<img loading="lazy" src="{pic}" alt="">' if pic else ""
        ready = sum(1 for m in rows if media.get(m["id"]))
        part_cards.append(
            f'<a class="ch" href="chapters/#part-{pk.lower()}">{img}'
            f'<div class="num serif">{PART_NUMERAL[pk]}</div>'
            f'<h3 class="serif">{e(pname.title())}</h3>'
            f'<div class="place">{len(chapters)} chapters &middot; '
            f'{len(rows)} moments</div>'
            f'<p>{e(part_blurb(pk))}</p>'
            f'<div class="count">{ready} WITH MEDIA</div></a>')

    quote = ""
    if featured["quote"]:
        src = f' <cite>{e(featured["quote_source"])}</cite>' if featured["quote_source"] else ""
        quote = (f'<blockquote><span class="serif">&ldquo;{e(featured["quote"])}&rdquo;'
                 f'</span>{src}</blockquote>')

    body = f"""
<section class="hero">
  <canvas id="river"></canvas>
  <div class="wrap inner">
    <div class="eyebrow">{WALKER} &middot; {DATES}</div>
    <h1 class="serif"><span class="w">Polarity</span><span class="w">of</span><span class="w">Grief</span></h1>
    <p class="lede">{TAGLINE} Every code printed in the book opens the moment you
    were just reading about &mdash; the photograph, the home video, the thing that
    actually happened.</p>
    <div class="meta">
      <div><span class="eyebrow">Moments</span><b>{stats['moments']}</b></div>
      <div><span class="eyebrow">Photographs</span><b>{stats['images']}</b></div>
      <div><span class="eyebrow">Film</span><b>{stats['runtime']}</b></div>
      <div><span class="eyebrow">Chapters</span><b>{stats['chapters']} across four parts</b></div>
    </div>
  </div>
</section>

<section class="map wrap">
  <div class="map-head">
    <div>
      <div class="eyebrow">The book</div>
      <h2 class="serif">Four parts, one current.</h2>
    </div>
    <p class="map-note">The site follows the book exactly. Start anywhere, or let a
    code in the margin bring you straight to the moment on the page in front of you.</p>
  </div>
  <div class="route">
    <svg viewBox="0 0 1200 150" preserveAspectRatio="none" aria-hidden="true">
      <path d="M0,110 C150,110 180,40 300,40 S420,120 600,120 S760,30 900,30 S1050,110 1200,110"/>
      <circle cx="150" cy="80" r="6"/><circle cx="450" cy="88" r="6"/>
      <circle cx="750" cy="60" r="6"/><circle cx="1050" cy="90" r="6"/>
    </svg>
  </div>
  <div class="chapters">
    {''.join(part_cards)}
  </div>
</section>

<section class="moment wrap">
  <div class="grid">
    <div class="frame">{feature_media}
      <div class="label">{e(featured["caption"] or featured["title"])}</div>
    </div>
    <div>
      <div class="page">{e(chapter_label(featured))}</div>
      <h2 class="serif">{e(featured["title"])}</h2>
      {quote}
      <div class="strip">{''.join(strip)}</div>
      <a class="go" href="m/{featured["id"]}/">Open this moment &rarr;</a>
    </div>
  </div>
</section>

<section class="qr" id="reading">
  <div class="wrap">
    <div class="eyebrow">Reading with the book</div>
    <h2 class="serif qr-h">Read the page. Scan the code. Watch the moment.</h2>
    <div class="row">
      <div class="step"><div class="k">01 &middot; IN THE BOOK</div>
        <div class="book">{e(BOOK_SNIPPET)}
          <div class="code"><div class="qrgrid" data-seed="10"></div></div>
        </div>
        <p>A small code sits in the margin, next to the story it belongs to.</p></div>
      <div class="step"><div class="k">02 &middot; ON THE PHONE</div>
        <div class="scan"><div class="beam"></div>
          <div class="code"><div class="qrgrid" data-seed="10"></div></div></div>
        <p>The phone camera reads it. No app, no account, nothing to install.</p></div>
      <div class="step"><div class="k">03 &middot; ON THIS SITE</div>
        <div class="land">
          <div class="eyebrow">{e(chapter_label(featured))}</div>
          <b>{e(featured["title"])}</b>
          <span>It opens this page &mdash; not the homepage.</span></div>
        <p>Every code points at a permanent address, so the book never goes stale.</p></div>
    </div>
  </div>
</section>

<section class="pol wrap">
  <div class="eyebrow">Where the title comes from</div>
  <h2 class="serif pol-h">Two poles of a single love.</h2>
  <div class="poles">
    <div class="pole sun"><div class="eyebrow">The sorrow</div>
      <p>&ldquo;Grief is like that. The sorrow and the peace are not two separate
      feelings competing for the same heart.&rdquo;</p></div>
    <div class="axis"></div>
    <div class="pole tide"><div class="eyebrow">The peace</div>
      <p>&ldquo;They are the two poles of a single love.&rdquo;</p></div>
  </div>
  <p class="pol-note">From the introduction to <i>Polarity of Grief</i>.</p>
</section>
"""
    return page(SITE_NAME, body, depth=0, hero_canvas=True,
                extra='<script defer src="assets/qr.js"></script>')


BOOK_SNIPPET = ("I counted him down, three, two, one, and he jumped at the exact "
                "right beat, zero hesitation.")


def part_blurb(pk):
    return {
        "One": "Who he was, and the seven places the family called home.",
        "Two": "The house Rob and Walker were building together.",
        "Three": "The fog, the fork in the road, and what came after.",
        "Four": "What he is doing now, and the next chapter.",
    }[pk]


def chapter_label(m):
    if m["chapter_no"]:
        return f"Chapter {m['chapter_no']} · {m['chapter_title']}"
    return m["chapter_title"] or f"Part {m['part']}"


def chapter_key(m):
    return (m["part"], m["chapter_no"], m["chapter_title"])


def chapter_url(m):
    n = m["chapter_no"] or "x"
    return f"c/{n}-{slug(m['chapter_title'])}/"


NUMBER_WORDS = {
    1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six",
    7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten", 11: "Eleven", 12: "Twelve",
    13: "Thirteen", 14: "Fourteen", 15: "Fifteen", 16: "Sixteen",
    17: "Seventeen", 18: "Eighteen", 19: "Nineteen", 20: "Twenty",
    21: "Twenty-one", 22: "Twenty-two", 23: "Twenty-three",
}


def spell(n):
    return NUMBER_WORDS.get(n, str(n))


def build_chapters_index(moments, media):
    sections = []
    for pk, pname in PART_NAMES.items():
        rows = [m for m in moments if m["part"] == pk]
        if not rows:
            continue
        chapters = OrderedDict()
        for m in rows:
            chapters.setdefault(chapter_key(m), []).append(m)
        items = []
        for key, ms in chapters.items():
            m0 = ms[0]
            pic = None
            for m in ms:
                pic = thumb_for(media.get(m["id"], []), "../")
                if pic:
                    break
            img = f'<img loading="lazy" src="{pic}" alt="">' if pic else '<div class="noimg"></div>'
            num = f'Chapter {m0["chapter_no"]}' if m0["chapter_no"] else "&mdash;"
            items.append(
                f'<a class="chrow" href="../{chapter_url(m0)}">{img}'
                f'<div><span class="n">{num}</span>'
                f'<h3 class="serif">{e(m0["chapter_title"])}</h3>'
                f'<span class="c">{len(ms)} moment{"s" if len(ms) != 1 else ""}</span>'
                f'</div></a>')
        sections.append(
            f'<section class="partsec" id="part-{pk.lower()}">'
            f'<div class="parthead"><span class="serif pn">{PART_NUMERAL[pk]}</span>'
            f'<div><div class="eyebrow">Part {pk}</div>'
            f'<h2 class="serif">{e(pname.title())}</h2>'
            f'<p>{e(part_blurb(pk))}</p></div></div>'
            f'<div class="chlist">{"".join(items)}</div></section>')

    n_ch = len({chapter_key(m) for m in moments})
    n_parts = len({m["part"] for m in moments})
    body = f"""
<section class="pagehead wrap">
  <div class="eyebrow">The book</div>
  <h1 class="serif">Chapters</h1>
  <p>{spell(n_ch)} chapters across {spell(n_parts).lower()} parts. Each one
  holds the moments that belong to it.</p>
</section>
<div class="wrap">{''.join(sections)}</div>
"""
    return page("Chapters", body, depth=1,
                description="Every part and chapter of Polarity of Grief.")


def build_chapter_page(m0, ms, media, moments):
    depth = 2
    up = depth_prefix(depth)
    cards = []
    for m in ms:
        pic = thumb_for(media.get(m["id"], []), up)
        img = f'<img loading="lazy" src="{pic}" alt="">' if pic else '<div class="noimg"></div>'
        kinds = media.get(m["id"], [])
        nv = sum(1 for x in kinds if x["type"] == "video")
        ni = sum(1 for x in kinds if x["type"] == "image")
        bits = []
        if nv:
            bits.append(f'{nv} film{"s" if nv != 1 else ""}')
        if ni:
            bits.append(f'{ni} photograph{"s" if ni != 1 else ""}')
        meta = " &middot; ".join(bits) or "Media still being gathered"
        cards.append(
            f'<a class="mcard" href="{up}m/{m["id"]}/">{img}'
            f'<div class="mc-body"><h3 class="serif">{e(m["title"])}</h3>'
            f'<span class="mc-meta">{meta}</span></div></a>')

    place = ms[0]["place"]
    sub = f'<div class="eyebrow">{e(place)}</div>' if place else ""
    body = f"""
<section class="pagehead wrap">
  <a class="back" href="{up}chapters/">&larr; All chapters</a>
  <div class="eyebrow">Part {m0['part']} &middot; {e(PART_NAMES[m0['part']].title())}</div>
  <h1 class="serif">{e(m0['chapter_title'])}</h1>
  {sub}
</section>
<div class="wrap"><div class="mgrid">{''.join(cards)}</div></div>
"""
    return page(m0["chapter_title"], body, depth=depth,
                description=f"Moments from {m0['chapter_title']} in Polarity of Grief.")


def build_moment_page(m, media, prev_m, next_m):
    depth = 2
    up = depth_prefix(depth)
    entries = media.get(m["id"], [])
    quote = ""
    if m["quote"]:
        src = f'<cite>{e(m["quote_source"])}</cite>' if m["quote_source"] else ""
        quote = (f'<blockquote class="passage"><p class="serif">&ldquo;{e(m["quote"])}'
                 f'&rdquo;</p>{src}</blockquote>')

    caption = f'<p class="cap">{e(m["caption"])}</p>' if m["caption"] else ""
    where = " &middot; ".join(x for x in (m["place"], m["year"]) if x)
    where_html = f'<div class="where">{e(where)}</div>' if where else ""

    nav = []
    if prev_m:
        nav.append(f'<a class="pn prev" href="{up}m/{prev_m["id"]}/">'
                   f'<span>Previous</span>{e(prev_m["title"])}</a>')
    if next_m:
        nav.append(f'<a class="pn next" href="{up}m/{next_m["id"]}/">'
                   f'<span>Next</span>{e(next_m["title"])}</a>')

    body = f"""
<article class="momentpage wrap">
  <a class="back" href="{up}{chapter_url(m)}">&larr; {e(m['chapter_title'])}</a>
  <div class="eyebrow">{e(chapter_label(m))}</div>
  <h1 class="serif">{e(m['title'])}</h1>
  {where_html}
  {quote}
  <div class="media">{media_block(entries, depth, m['title'])}</div>
  {caption}
  <div class="pagenav">{''.join(nav)}</div>
  <div class="permalink">Permanent address for this moment:
    <code>{BASE}m/{m['id']}/</code></div>
</article>
"""
    return page(m["title"], body, depth=depth,
                description=(m["caption"] or m["quote"][:150] or m["title"]))


def build_moments_index(moments, media):
    rows = []
    for m in moments:
        pic = thumb_for(media.get(m["id"], []), "../")
        img = f'<img loading="lazy" src="{pic}" alt="">' if pic else '<div class="noimg"></div>'
        rows.append(
            f'<a class="mcard" href="../m/{m["id"]}/">{img}'
            f'<div class="mc-body"><span class="mc-id">{m["id"]}</span>'
            f'<h3 class="serif">{e(m["title"])}</h3>'
            f'<span class="mc-meta">{e(chapter_label(m))}</span></div></a>')
    body = f"""
<section class="pagehead wrap">
  <div class="eyebrow">Everything, in book order</div>
  <h1 class="serif">Every moment</h1>
  <p>{len(moments)} moments. Each has a permanent address that a printed code
  can point at.</p>
</section>
<div class="wrap"><div class="mgrid">{''.join(rows)}</div></div>
"""
    return page("Every moment", body, depth=1,
                description="Every moment in the Polarity of Grief archive.")


def build_404():
    body = f"""
<section class="pagehead wrap" style="padding-block:120px 90px">
  <div class="eyebrow">That address isn't here</div>
  <h1 class="serif">We couldn't find that moment.</h1>
  <p>If you scanned a code from the book and landed here, the moment may not be
  published yet. Try the chapters, or the full list of moments.</p>
  <p style="margin-top:26px"><a class="go" href="{BASE}chapters/">Browse the chapters &rarr;</a>
  &nbsp; <a class="go" href="{BASE}moments/">Every moment &rarr;</a></p>
</section>
"""
    return page("Not found", body, depth=0, absolute=True)


# ---------------------------------------------------------------- main

def main():
    if not os.path.exists(MANIFEST):
        print("No media manifest yet — run process_media.py first.", file=sys.stderr)
        media = {}
    else:
        with open(MANIFEST, encoding="utf-8") as f:
            media = json.load(f)

    with open(MOMENTS_CSV, encoding="utf-8") as f:
        moments = [r for r in csv.DictReader(f)]
    moments.sort(key=lambda m: m["id"])

    os.makedirs(os.path.join(PUBLIC, "assets"), exist_ok=True)
    shutil.copy(os.path.join(HERE, "assets", "site.css"),
                os.path.join(PUBLIC, "assets", "site.css"))
    shutil.copy(os.path.join(HERE, "assets", "qr.js"),
                os.path.join(PUBLIC, "assets", "qr.js"))

    images = sum(1 for v in media.values() for x in v if x["type"] == "image")
    videos = [x for v in media.values() for x in v if x["type"] == "video"]
    secs = sum(x.get("seconds") or 0 for x in videos)
    hours, rem = divmod(int(secs), 3600)
    mins = rem // 60
    runtime = f"{hours}h {mins}m" if hours else f"{mins} min"
    chapters = len({(m["part"], m["chapter_title"]) for m in moments})
    stats = {"moments": len(moments), "images": images, "videos": len(videos),
             "runtime": runtime, "chapters": chapters}

    written = 0

    def write(relpath, text):
        nonlocal written
        path = os.path.join(PUBLIC, relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        written += 1

    write("index.html", build_home(moments, media, stats))
    write("chapters/index.html", build_chapters_index(moments, media))
    write("moments/index.html", build_moments_index(moments, media))
    write("404.html", build_404())

    groups = OrderedDict()
    for m in moments:
        groups.setdefault(chapter_key(m), []).append(m)
    for key, ms in groups.items():
        write(chapter_url(ms[0]) + "index.html",
              build_chapter_page(ms[0], ms, media, moments))

    for i, m in enumerate(moments):
        prev_m = moments[i - 1] if i else None
        next_m = moments[i + 1] if i + 1 < len(moments) else None
        write(f"m/{m['id']}/index.html", build_moment_page(m, media, prev_m, next_m))

    # a machine-readable index, handy for generating the QR sheet later
    write("moments.json", json.dumps(
        [{"id": m["id"], "url": f"{BASE}m/{m['id']}/", "title": m["title"],
          "part": m["part"], "chapter": m["chapter_title"],
          "media": len(media.get(m["id"], [])), "status": m["status"]}
         for m in moments], indent=1, ensure_ascii=False))

    print(f"{written} pages  ·  {stats['moments']} moments  ·  "
          f"{images} photographs  ·  {len(videos)} films ({runtime})  ·  "
          f"{len(groups)} chapters")
    unpublished = [m["id"] for m in moments if not media.get(m["id"])]
    if unpublished:
        print(f"{len(unpublished)} moments still have no media: "
              f"{', '.join(unpublished)}")


if __name__ == "__main__":
    main()
