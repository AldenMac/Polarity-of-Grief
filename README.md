# Polarity of Grief — companion site

The companion to Rob McFadden's book about his son, Anthon Walker McFadden
(25 July 2005 – 5 March 2022).

A code printed beside a passage in the book opens the moment that passage is
about: the photograph, the home video, the thing that actually happened.

## The one rule

**A moment's URL is permanent.** Once `/m/w014/` is printed in a book, it has
to keep working for as long as that book exists on a shelf. Moment IDs
(`w001`…`w045`) never change, never get reused, and never get renumbered.

Page numbers are never used as addresses. Pagination differs between the
hardcover, the paperback and the ebook, and it changes again on every reprint.
The ID is the contract; everything else on this site can be rebuilt.

## How it works

Three files, in order:

`content/moments.csv` is the source of truth. One row per moment, with its
permanent ID, the part and chapter it belongs to, a verbatim quote from the
manuscript, a caption, and a pipe-separated list of source filenames as they
exist in the archive folder above this one. Nothing else in the project holds
content — if it isn't in this file, it isn't on the site.

`process_media.py` reads that CSV, finds every source file, and writes
web-ready derivatives into `public/media/`. Photographs become JPEGs at 1800px
with 720px thumbnails; HEIC is converted because no browser renders it. Video
becomes H.264 MP4 at 1280px with a poster frame pulled from early in the clip.
Every derivative is named after its moment ID, so nothing depends on the
original filenames — which are inconsistent, and in a few cases misspelled. It
also writes `public/media/manifest.json`, including real measured runtimes, so
the site never has to guess how long a film is. Re-running it skips work that
is already done; pass `--force` to redo everything.

`build.py` reads the CSV and the manifest and writes the whole site into
`public/`: the home page, a chapter index, a page per chapter, a page per
moment, a flat index of every moment, a 404, and `moments.json` — a
machine-readable list of every permanent URL, which is what the QR sheet gets
generated from when the book goes to print.

```
python3 process_media.py --jobs 4      # slow; only needed when media changes
python3 build.py                       # fast; run after any CSV edit
cd public && python3 -m http.server    # look at it
```

### Finishing the video

All 99 photographs are done. Twenty-nine of the forty-one films are
transcoded; the remaining twelve are the long ones — the funeral music, the
vigil, the haka, and the twenty-eight-minute well story. They were left
unfinished only because the machine that built this had a hard limit on how
long any single command could run. Running

```
python3 process_media.py --jobs 4
```

on a Mac finishes them in a few minutes and picks up exactly where it stopped:
nothing already done is redone. Then `python3 build.py` again, and the film
counts, runtimes and players appear on their moment pages.

Long films are encoded in 45-second pieces under `/tmp/pog-parts` and joined
without re-encoding, so an interrupted run never loses more than one piece.

## Design

The site is the "River" direction from the nine design studies in
`../Website Mockups/`. Dark, cinematic, the current of a river running under
the hero. All of its CSS lives in `assets/site.css`; the top two thirds of
that file is the original mockup untouched, and the bottom third extends it to
the page types the mockup never had.

Fonts are Bodoni Moda and Libre Franklin, loaded from Google Fonts.

## What is not in this repo

The transcoded video is gitignored. Ninety minutes of footage is too much for
git, and Cloudflare Pages rejects any single file over 25 MB. In production
the films are served from a video host — Bunny Stream or Cloudflare Stream —
and `build.py` is the one place that would need to change to point at them.
Run `process_media.py` after cloning to rebuild them locally.

The source archive itself — the original photographs, films and audio, and the
manuscript — lives in the folder above this one and is deliberately not part of
the repo.

## Deploying

`public/` is a plain static directory with no build step and no server-side
anything. Point Cloudflare Pages (or Netlify, or S3) at it. Configure
`404.html` as the not-found page so a mistyped or not-yet-published code lands
somewhere kind instead of on a server error.
