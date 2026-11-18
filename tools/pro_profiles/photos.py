"""Find, approve and download freely licensed player photos (Wikimedia Commons).

Run from `tools/`:
    python -m pro_profiles.photos candidates [--out .superpowers/photo-candidates]
    python -m pro_profiles.photos approve <player_id> --focus X,Y
    python -m pro_profiles.photos download

Only a human approves photos. `candidates` never writes photos.json.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .load import CONTENT_DIR, load_content

PHOTOS_PATH = CONTENT_DIR / "photos.json"
PHOTO_DIR = Path(__file__).resolve().parents[2] / "frontend/badminton-ai/public/pro-data/photos"
DEFAULT_OUT = Path(__file__).resolve().parents[2] / ".superpowers/photo-candidates"
DEFAULT_FOCUS = (50, 30)
USER_AGENT = "shuttleye-photo-fetch/0.1"
MIN_INTERVAL_SEC = 2.0
MAX_RETRIES = 4
MAX_RETRY_WAIT_SEC = 60
THUMB_WIDTH = 400

# CC BY / CC BY-SA (any version), CC0, public domain. NC, ND and fair use are out.
_ALLOWED = re.compile(
    r"^(cc[ -]by(-sa)?([ -]\d+(\.\d+)?)?(\s.*)?|cc0(\s.*)?|public domain(\s.*)?)$", re.IGNORECASE
)


_RESTRICTED_TOKENS = {"nc", "nd"}  # NonCommercial / NoDerivatives, in any spelling


def licence_allowed(short_name: str) -> bool:
    name = (short_name or "").strip()
    if _RESTRICTED_TOKENS & set(re.split(r"[^a-z0-9]+", name.lower())):
        return False
    return bool(_ALLOWED.match(name))


def _plain(markup: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]*>", "", markup or "")).split())


def credit(author_html: str, licence: str) -> str:
    return f"Photo: {_plain(author_html)}, {licence}"


def parse_candidate(page: dict) -> dict | None:
    """Turn one Commons `pages` entry into a candidate, or None if not usable."""
    infos = page.get("imageinfo") or []
    if not infos:
        return None
    info = infos[0]
    meta = info.get("extmetadata") or {}
    licence = (meta.get("LicenseShortName") or {}).get("value", "")
    if not licence_allowed(licence):
        return None
    return {
        "sourceUrl": info.get("descriptionurl", ""),
        "thumbUrl": info.get("thumburl", ""),
        "author": _plain((meta.get("Artist") or {}).get("value", "")) or "Unknown",
        "licence": licence,
    }


def parse_focus(text: str) -> tuple[int, int]:
    parts = text.split(",")
    if len(parts) != 2:
        raise ValueError("focus must be X,Y")
    x, y = (int(p) for p in parts)
    if not (0 <= x <= 100 and 0 <= y <= 100):
        raise ValueError("focus values must be 0-100")
    return x, y


def add_approval(photos: dict, pid: str, cand: dict, focus: tuple[int, int]) -> dict:
    out = dict(photos)
    out[pid] = {
        "sourceUrl": cand["sourceUrl"],
        "author": cand["author"],
        "licence": cand["licence"],
        "focusX": focus[0],
        "focusY": focus[1],
    }
    return out


def render_contact_sheet(cands: dict[str, dict]) -> str:
    e = html.escape
    cards = []
    for pid, c in cands.items():
        cmd = f"python -m pro_profiles.photos approve {pid} --focus {DEFAULT_FOCUS[0]},{DEFAULT_FOCUS[1]}"
        cards.append(
            f'<div class="card"><img src="{e(c["thumbUrl"])}" alt="{e(c["name"])}" loading="lazy">'
            f'<h2>{e(c["name"])}</h2>'
            f'<p>{e(c["licence"])} &middot; {e(c["author"])}</p>'
            f'<p><a href="{e(c["sourceUrl"])}">source</a></p>'
            f'<label>focus <input class="fx" value="{DEFAULT_FOCUS[0]}" size="3">,'
            f'<input class="fy" value="{DEFAULT_FOCUS[1]}" size="3"></label>'
            f'<pre data-id="{e(pid)}">{e(cmd)}</pre></div>'
        )
    return (
        "<!doctype html><meta charset=utf-8><title>Photo candidates</title>"
        "<style>body{font:14px system-ui;margin:16px}.grid{display:grid;gap:12px;"
        "grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}.card{border:1px solid #ccc;"
        "padding:8px;border-radius:6px}img{width:100%;height:260px;object-fit:cover}"
        "h2{font-size:16px;margin:6px 0}pre{white-space:pre-wrap;background:#eee;padding:6px}</style>"
        f"<h1>Photo candidates ({len(cands)})</h1><div class=grid>{''.join(cards)}</div>"
        "<script>document.querySelectorAll('.card').forEach(c=>{const p=c.querySelector('pre'),"
        "x=c.querySelector('.fx'),y=c.querySelector('.fy');const u=()=>p.textContent="
        "'python -m pro_profiles.photos approve '+p.dataset.id+' --focus '+x.value+','+y.value;"
        "x.oninput=u;y.oninput=u;});</script>\n"
    )


# ---- network (not unit tested) ----

_last_request = 0.0


def _get(url: str) -> bytes:
    global _last_request
    for attempt in range(MAX_RETRIES + 1):
        wait = MIN_INTERVAL_SEC - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            if err.code == 429 and attempt < MAX_RETRIES:
                retry_after = err.headers.get("Retry-After", "")
                time.sleep(min(float(retry_after) if retry_after.isdigit() else 10 * (attempt + 1), MAX_RETRY_WAIT_SEC))
                continue
            raise
    raise RuntimeError("unreachable")


def _api(host: str, **params) -> dict:
    qs = urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    return json.loads(_get(f"https://{host}/w/api.php?{qs}"))


def find_candidate(name: str) -> dict | None:
    wp = _api("en.wikipedia.org", action="query", titles=name, prop="pageimages",
              piprop="name", redirects="1")
    pages = wp.get("query", {}).get("pages", [])
    filename = pages[0].get("pageimage") if pages else None
    if not filename:
        return None
    cm = _api("commons.wikimedia.org", action="query", titles=f"File:{filename}",
              prop="imageinfo", iiprop="url|extmetadata", iiurlwidth=str(THUMB_WIDTH))
    cpages = cm.get("query", {}).get("pages", [])
    return parse_candidate(cpages[0]) if cpages else None


def cmd_candidates(out: Path) -> None:
    players = load_content("players")
    cands: dict[str, dict] = {}
    for pid, info in players.items():
        try:
            c = find_candidate(info["name"])
        except (urllib.error.URLError, socket.timeout, TimeoutError, ValueError, KeyError) as err:
            print(f"{pid}: lookup failed ({err})", file=sys.stderr)
            continue
        print(f"{pid}: {'candidate ' + c['licence'] if c else 'none'}")
        if c:
            cands[pid] = {"name": info["name"], **c}
    out.mkdir(parents=True, exist_ok=True)
    (out / "candidates.json").write_text(json.dumps(cands, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "contact-sheet.html").write_text(render_contact_sheet(cands), encoding="utf-8")
    print(f"{len(cands)}/{len(players)} players have a candidate: {out / 'contact-sheet.html'}")


def _load_photos() -> dict:
    return json.loads(PHOTOS_PATH.read_text(encoding="utf-8")) if PHOTOS_PATH.exists() else {}


def validate_approval(pid: str, players: dict, cands: dict) -> dict:
    """Return the candidate for pid, or raise ValueError with a clear message."""
    if pid not in players:
        raise ValueError(f"unknown player id: {pid}")
    if pid not in cands:
        raise ValueError(f"no candidate for {pid}")
    if not licence_allowed(cands[pid].get("licence", "")):
        raise ValueError(f"licence not allowed for {pid}: {cands[pid].get('licence')!r}")
    return cands[pid]


def cmd_approve(pid: str, focus: str, out: Path) -> None:
    path = out / "candidates.json"
    if not path.exists():
        sys.exit(f"{path} not found; run `candidates` first")
    try:
        xy = parse_focus(focus)
        cand = validate_approval(pid, load_content("players"), json.loads(path.read_text(encoding="utf-8")))
    except ValueError as err:
        sys.exit(f"error: {err}")
    photos = add_approval(_load_photos(), pid, cand, xy)
    PHOTOS_PATH.write_text(json.dumps(photos, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"approved {pid}")


def commons_filename(source_url: str) -> str:
    if "/wiki/File:" not in source_url:
        raise ValueError(f"unexpected sourceUrl (no /wiki/File:): {source_url}")
    return urllib.parse.unquote(source_url.split("/wiki/File:", 1)[1])


def is_jpeg(data: bytes) -> bool:
    return data[:2] == b"\xff\xd8"


def cmd_download() -> None:
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    failed = []
    for pid, p in sorted(_load_photos().items()):
        try:
            filename = commons_filename(p["sourceUrl"])
            url = (f"https://commons.wikimedia.org/wiki/Special:FilePath/"
                   f"{urllib.parse.quote(filename)}?width={THUMB_WIDTH}")
            data = _get(url)
            if not is_jpeg(data):
                raise ValueError("thumbnail is not a JPEG; pick another photo or convert it manually")
        except (ValueError, urllib.error.URLError, socket.timeout, TimeoutError) as err:
            print(f"{pid}: FAILED ({err})", file=sys.stderr)
            failed.append(pid)
            continue
        (PHOTO_DIR / f"{pid}.jpg").write_bytes(data)
        print(f"downloaded {pid}")
    if failed:
        sys.exit(f"download failed for: {', '.join(failed)}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m pro_profiles.photos")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("candidates")
    c.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = sub.add_parser("approve")
    a.add_argument("player_id")
    a.add_argument("--focus", default=f"{DEFAULT_FOCUS[0]},{DEFAULT_FOCUS[1]}")
    a.add_argument("--out", type=Path, default=DEFAULT_OUT)
    sub.add_parser("download")
    args = ap.parse_args(argv)
    if args.cmd == "candidates":
        cmd_candidates(args.out)
    elif args.cmd == "approve":
        cmd_approve(args.player_id, args.focus, args.out)
    else:
        cmd_download()


if __name__ == "__main__":
    main()
