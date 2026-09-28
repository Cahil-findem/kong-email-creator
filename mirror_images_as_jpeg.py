"""Re-host a company's blog featured images as JPEG when email clients can't render them.

Some sites serve WebP or AVIF (Genesys serves every blog image as WebP;
YouTube's signed thumbnails come back as AVIF even with a .jpg name). Outlook
desktop renders neither, so the card image shows blank. This fetches each
featured image, detects the real format from the bytes rather than the URL,
and for anything other than JPEG/PNG/GIF converts to JPEG, uploads it to the
public `email-assets` bucket, and points the row at the copy.

Usage:
    python mirror_images_as_jpeg.py --company Genesys            # dry run
    python mirror_images_as_jpeg.py --company Genesys --apply
"""
import argparse
import io
import os
import re

import requests
from dotenv import load_dotenv
from PIL import Image
from supabase import create_client

EMAIL_SAFE = {"JPEG", "PNG", "GIF"}
BUCKET = "email-assets"
MAX_WIDTH = 1200
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def to_jpeg(data):
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        flat = Image.new("RGB", im.size, (255, 255, 255))
        flat.paste(im, mask=im.split()[-1])
        im = flat
    else:
        im = im.convert("RGB")
    if im.width > MAX_WIDTH:
        im = im.resize((MAX_WIDTH, round(im.height * MAX_WIDTH / im.width)), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85, optimize=True, progressive=True)
    return out.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    load_dotenv()
    sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    bucket = sb.storage.from_(BUCKET)
    rows = sb.table("blog_posts").select("id,title,featured_image") \
        .eq("company", args.company).execute().data

    counts = {"already_safe": 0, "hosted": 0, "converted": 0, "failed": 0, "no_image": 0}
    for r in rows:
        url = r.get("featured_image") or ""
        if not url:
            counts["no_image"] += 1
            continue
        if f"/{BUCKET}/" in url:
            counts["hosted"] += 1
            continue
        try:
            resp = requests.get(url, headers={"User-Agent": UA}, timeout=30)
            resp.raise_for_status()
            fmt = Image.open(io.BytesIO(resp.content)).format
        except Exception as e:
            counts["failed"] += 1
            print(f"  FAIL id={r['id']} {type(e).__name__}: {url[:80]}")
            continue
        if fmt in EMAIL_SAFE:
            counts["already_safe"] += 1
            continue
        path = f"{slug(args.company)}/{r['id']}.jpg"
        print(f"  {fmt:5s} -> JPEG  id={r['id']}  {r['title'][:60]}")
        if args.apply:
            jpeg = to_jpeg(resp.content)
            try:
                bucket.upload(path, jpeg, {"content-type": "image/jpeg", "upsert": "true"})
            except Exception as e:
                if "exists" in str(e) or "Duplicate" in str(e):
                    bucket.update(path, jpeg, {"content-type": "image/jpeg"})
                else:
                    raise
            sb.table("blog_posts").update({"featured_image": bucket.get_public_url(path)}) \
                .eq("id", r["id"]).execute()
        counts["converted"] += 1

    mode = "converted" if args.apply else "would convert"
    print(f"\n{args.company}: {counts['converted']} {mode} | {counts['already_safe']} already "
          f"email-safe | {counts['hosted']} already hosted | {counts['no_image']} no image | "
          f"{counts['failed']} failed")
    if not args.apply:
        print("Dry run. Re-run with --apply.")


if __name__ == "__main__":
    main()
