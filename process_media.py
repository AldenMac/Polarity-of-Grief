#!/usr/bin/env python3
"""
Turn the source archive into web media.

Reads content/moments.csv, finds every file listed in the `media` column,
and produces web-ready derivatives in public/media/.

  photographs -> public/media/img/<id>-<n>.jpg   (max 1800px, quality 82)
                 public/media/img/<id>-<n>-thumb.jpg (max 720px, quality 74)
  video       -> public/media/video/<id>-<n>.mp4 (H.264, max 1280 wide, faststart)
                 public/media/img/<id>-<n>-poster.jpg

HEIC is converted to JPEG because browsers do not render HEIC.
Every derivative is named after its moment id, so nothing depends on the
original filenames, which are inconsistent and contain typos.

Writes public/media/manifest.json describing what was produced, including
video durations, so the site can show real runtimes instead of guesses.

Safe to re-run: existing derivatives are skipped unless --force.
"""

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.dirname(HERE)          # the Polarity of Grief folder
MOMENTS = os.path.join(HERE, "content", "moments.csv")
IMG_OUT = os.path.join(HERE, "public", "media", "img")
VID_OUT = os.path.join(HERE, "public", "media", "video")
MANIFEST = os.path.join(HERE, "public", "media", "manifest.json")

VIDEO_EXT = (".mov", ".m4v", ".mp4", ".avi")
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff")


DEADLINE = None      # set by --budget; None means run to completion


class OutOfTime(Exception):
    """The budget ran out mid-encode. Not a failure — just unfinished."""


def run(cmd):
    timeout = None
    if DEADLINE is not None:
        timeout = DEADLINE - time.monotonic()
        if timeout <= 0:
            raise OutOfTime()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise OutOfTime()
    if p.returncode != 0:
        raise RuntimeError(" ".join(cmd[:3]) + " failed: " + p.stderr.strip()[-400:])


STAGE_DIR = "/tmp"


def run_retry(cmd, tries=3, wait=4):
    """The archive is a mounted volume and its reads go flaky under parallel
    load — ffmpeg reports "moov atom not found" on files that read perfectly
    well a moment later. Ask again before believing it."""
    for attempt in range(1, tries + 1):
        try:
            return run(cmd)
        except OutOfTime:
            raise
        except RuntimeError:
            if attempt == tries:
                raise
            time.sleep(wait * attempt)


def heic_to_jpeg(src, dst):
    """Last resort for the HEIC files ImageMagick's delegate won't decode.

    Apple's newer 'tmap' HEICs (the ones carrying an HDR gain map) come back
    as 'no images defined'. libheif via pillow-heif reads them fine.
    """
    import pillow_heif
    from PIL import Image
    pillow_heif.register_heif_opener()
    im = Image.open(src)
    im.convert("RGB").save(dst, quality=90, optimize=True)


def duration(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True)
    try:
        return round(float(p.stdout.strip()), 1)
    except ValueError:
        return None


def mmss(seconds):
    if seconds is None:
        return None
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"


def do_image(src, stem, force):
    full = os.path.join(IMG_OUT, stem + ".jpg")
    thumb = os.path.join(IMG_OUT, stem + "-thumb.jpg")
    if force or not os.path.exists(full):
        try:
            run_retry(["convert", src + "[0]", "-auto-orient",
                       "-resize", "1800x1800>", "-strip",
                       "-interlace", "Plane", "-quality", "82", full])
        except RuntimeError:
            if os.path.splitext(src)[1].lower() not in (".heic", ".heif"):
                raise
            fd, raw = tempfile.mkstemp(suffix=".jpg", dir=STAGE_DIR)
            os.close(fd)
            try:
                heic_to_jpeg(src, raw)
                run(["convert", raw, "-auto-orient", "-resize", "1800x1800>",
                     "-strip", "-interlace", "Plane", "-quality", "82", full])
            finally:
                try:
                    os.remove(raw)
                except OSError:
                    pass
    if force or not os.path.exists(thumb):
        run(["convert", full, "-resize", "720x720>", "-strip",
             "-quality", "74", thumb])
    w = h = None
    p = subprocess.run(["identify", "-format", "%w %h", full],
                       capture_output=True, text=True)
    if p.returncode == 0:
        w, h = (int(x) for x in p.stdout.split())
    return {"type": "image", "src": f"media/img/{stem}.jpg",
            "thumb": f"media/img/{stem}-thumb.jpg", "w": w, "h": h}


ENCODE = ["-vf", "scale='min(1280,iw)':-2",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
          "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "96k", "-ac", "2"]

PARTS_DIR = "/tmp/pog-parts"
CHUNK = 45           # seconds of footage per piece
CHUNK_ABOVE = 50     # only split films longer than this

# Much of this archive is 4K, and scaling 4K down to 1280 is expensive: about
# two and a half seconds of footage per second of wall clock on four cores.
# Small chunks keep every piece finishable, which is what makes --budget work.


def encode_chunked(local, out, stem, total):
    """Encode a long film in pieces, then join them without re-encoding.

    Under --budget a single long encode can never finish: it gets cut off and
    the work is thrown away, so the film never lands no matter how many times
    you run. Pieces are small enough to finish, and each one that lands stays
    landed, so successive runs converge.
    """
    partdir = os.path.join(PARTS_DIR, stem)
    os.makedirs(partdir, exist_ok=True)
    n = int(math.ceil(total / CHUNK))
    parts = []
    for i in range(n):
        part = os.path.join(partdir, "%04d.mp4" % i)
        parts.append(part)
        if os.path.exists(part) and duration(part) is not None:
            continue
        run_retry(["ffmpeg", "-y", "-v", "error", "-ss", str(i * CHUNK),
                   "-t", str(CHUNK), "-i", local] + ENCODE + [part])

    listfile = os.path.join(partdir, "list.txt")
    with open(listfile, "w", encoding="utf-8") as f:
        for p in parts:
            f.write("file '%s'\n" % p.replace("'", r"'\''"))
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", listfile, "-c", "copy", "-movflags", "+faststart", out])
    shutil.rmtree(partdir, ignore_errors=True)


def do_video(src, stem, force):
    out = os.path.join(VID_OUT, stem + ".mp4")
    poster = os.path.join(IMG_OUT, stem + "-poster.jpg")
    if force or not os.path.exists(out) or duration(out) is None:
        total = duration(src)
        if total and total > CHUNK_ABOVE:
            encode_chunked(src, out, stem, total)
        else:
            run_retry(["ffmpeg", "-y", "-v", "error", "-i", src]
                      + ENCODE + ["-movflags", "+faststart", out])
    secs = duration(out)
    if force or not os.path.exists(poster):
        at = min(1.5, (secs or 2) / 3)
        run(["ffmpeg", "-y", "-v", "error", "-ss", str(at), "-i", out,
             "-vframes", "1", "-vf", "scale='min(1280,iw)':-2",
             "-q:v", "4", poster])
    return {"type": "video", "src": f"media/video/{stem}.mp4",
            "poster": f"media/img/{stem}-poster.jpg",
            "seconds": secs, "runtime": mmss(secs)}


def existing(kind, stem):
    """Describe a derivative that is already on disk, doing no work.

    Used when a run runs out of time: the manifest still needs to list
    everything finished on earlier runs, or the site would lose media it
    already has.
    """
    if kind == "image":
        full = os.path.join(IMG_OUT, stem + ".jpg")
        thumb = os.path.join(IMG_OUT, stem + "-thumb.jpg")
        if not (os.path.exists(full) and os.path.exists(thumb)):
            return None
        w = h = None
        p = subprocess.run(["identify", "-format", "%w %h", full],
                           capture_output=True, text=True)
        if p.returncode == 0:
            try:
                w, h = (int(x) for x in p.stdout.split())
            except ValueError:
                pass
        return {"type": "image", "src": f"media/img/{stem}.jpg",
                "thumb": f"media/img/{stem}-thumb.jpg", "w": w, "h": h}

    out = os.path.join(VID_OUT, stem + ".mp4")
    poster = os.path.join(IMG_OUT, stem + "-poster.jpg")
    if not os.path.exists(out) or not os.path.exists(poster):
        return None
    secs = duration(out)
    if secs is None:          # a stub left behind by an interrupted encode
        return None
    return {"type": "video", "src": f"media/video/{stem}.mp4",
            "poster": f"media/img/{stem}-poster.jpg",
            "seconds": secs, "runtime": mmss(secs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--images-only", action="store_true")
    ap.add_argument("--budget", type=float, default=0, metavar="SECONDS",
                    help="stop starting new work after this long. Anything "
                         "already finished still lands in the manifest, so "
                         "re-running picks up exactly where it stopped.")
    args = ap.parse_args()
    global DEADLINE
    DEADLINE = (time.monotonic() + args.budget) if args.budget else None
    deadline = DEADLINE

    os.makedirs(IMG_OUT, exist_ok=True)
    os.makedirs(VID_OUT, exist_ok=True)

    jobs, missing = [], []
    with open(MOMENTS, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            files = [x for x in row["media"].split("|") if x.strip()]
            for i, rel in enumerate(files, 1):
                src = os.path.join(ARCHIVE, rel)
                if not os.path.exists(src):
                    missing.append((row["id"], rel))
                    continue
                ext = os.path.splitext(rel)[1].lower()
                stem = f"{row['id']}-{i}"
                if ext in VIDEO_EXT:
                    if not args.images_only:
                        jobs.append(("video", src, stem, rel, row["id"]))
                elif ext in IMAGE_EXT:
                    jobs.append(("image", src, stem, rel, row["id"]))
                else:
                    missing.append((row["id"], rel + " (unsupported type)"))

    for mid, rel in missing:
        print(f"  missing: {mid}  {rel}", file=sys.stderr)

    # Cheapest work first: images, then the shortest films. If the run is cut
    # short, what got done is the widest useful slice rather than one epic.
    jobs.sort(key=lambda j: (j[0] == "video", os.path.getsize(j[1])))

    manifest, failures, deferred = {}, [], []
    total = len(jobs)
    done = 0

    def work(job):
        kind, src, stem, rel, mid = job
        if deadline and time.monotonic() > deadline:
            # Out of time. Report anything already on disk so the manifest
            # stays complete, and leave the rest for the next run.
            entry = existing(kind, stem)
            if entry:
                entry["source"] = rel
                return mid, entry, None
            return mid, None, "DEFER " + rel
        try:
            entry = do_image(src, stem, args.force) if kind == "image" \
                else do_video(src, stem, args.force)
            entry["source"] = rel
            return mid, entry, None
        except OutOfTime:
            entry = existing(kind, stem)
            if entry:
                entry["source"] = rel
                return mid, entry, None
            return mid, None, "DEFER " + rel
        except Exception as e:
            return mid, None, f"{rel}: {e}"

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for mid, entry, err in pool.map(work, jobs):
            done += 1
            if err and err.startswith("DEFER "):
                deferred.append(err[6:])
            elif err:
                failures.append(err)
                print(f"  [{done}/{total}] FAILED {err}", file=sys.stderr)
            else:
                manifest.setdefault(mid, []).append(entry)
                print(f"  [{done}/{total}] {entry['src']}", flush=True)

    # keep each moment's media in the order the csv listed it
    for mid in manifest:
        manifest[mid].sort(key=lambda e: int(
            os.path.basename(e["src"]).split("-")[1].split(".")[0]))

    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)

    imgs = sum(1 for v in manifest.values() for e in v if e["type"] == "image")
    vids = sum(1 for v in manifest.values() for e in v if e["type"] == "video")
    secs = sum(e.get("seconds") or 0 for v in manifest.values() for e in v)
    print(f"\n{imgs} images, {vids} videos ({secs/60:.1f} min) "
          f"across {len(manifest)} moments")
    if missing:
        print(f"{len(missing)} source files missing")
    if deferred:
        print(f"{len(deferred)} still to do — run again to continue")
    if failures:
        print(f"{len(failures)} failed")
        return 1
    return 2 if deferred else 0


if __name__ == "__main__":
    sys.exit(main())
