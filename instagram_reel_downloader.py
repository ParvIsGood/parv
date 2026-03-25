#!/usr/bin/env python3
"""
Small CLI helper to automate downloading Instagram Reels.

The script relies on the `instaloader` library to fetch public reels without a
login. For private reels, provide a username/password or an existing
`sessionid` cookie (recommended for non-interactive use).
"""

import argparse
import getpass
import re
import sys
from pathlib import Path
from typing import Iterable, Optional

from instaloader import (
    ConnectionException,
    Instaloader,
    InstaloaderException,
    InvalidArgumentException,
    Post,
)

SHORTCODE_RE = re.compile(r"(?:instagram\.com/(?:reel|reels|p|tv)/)([A-Za-z0-9_-]+)")


def extract_shortcode(candidate: str) -> str:
    """
    Extract a reel shortcode from a full URL or a raw shortcode string.
    """
    match = SHORTCODE_RE.search(candidate)
    if match:
        return match.group(1)
    candidate = candidate.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{5,}", candidate):
        return candidate
    raise ValueError(f"Could not find a reel shortcode in: {candidate}")


def configure_loader(output_dir: Path) -> Instaloader:
    loader = Instaloader(dirname_pattern=str(output_dir / "{target}"), filename_pattern="{shortcode}")

    def maybe_set(attr: str, value):
        if hasattr(loader, attr):
            setattr(loader, attr, value)

    maybe_set("download_comments", False)
    maybe_set("save_metadata", False)
    maybe_set("compress_json", False)
    maybe_set("download_geotags", False)
    maybe_set("download_video_thumbnails", False)
    maybe_set("post_metadata_txt_pattern", "")

    return loader


def apply_auth(loader: Instaloader, username: Optional[str], password: Optional[str], sessionid: Optional[str]) -> None:
    ctx = loader.context
    if sessionid:
        # sessionid cookie avoids interactive login prompts; works for accounts with existing access.
        for domain in [".instagram.com", "instagram.com"]:
            ctx._session.cookies.set("sessionid", sessionid, domain=domain)
        ctx.log("Using provided sessionid cookie for authentication.")
        return
    if username:
        pwd = password or getpass.getpass("Instagram password (input hidden): ")
        ctx.log(f"Logging in as {username}...")
        loader.login(username, pwd)
        return
    ctx.log("No credentials provided. Public reels only.")


def download_reel(loader: Instaloader, shortcode: str, base_dir: Path) -> Path:
    post = Post.from_shortcode(loader.context, shortcode)
    loader.download_post(post, target=shortcode)
    target_dir = base_dir / shortcode
    video = next(target_dir.glob(f"{shortcode}*.mp4"), None)
    return video or target_dir


def download_many(urls: Iterable[str], output_dir: Path, username: Optional[str], password: Optional[str], sessionid: Optional[str]) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    loader = configure_loader(output_dir)
    apply_auth(loader, username, password, sessionid)
    successes = 0

    for raw in urls:
        try:
            shortcode = extract_shortcode(raw)
            dest = download_reel(loader, shortcode, output_dir)
            print(f"[ok] Saved {shortcode} -> {dest}")
            successes += 1
        except (InvalidArgumentException, ConnectionException, InstaloaderException, ValueError) as exc:
            print(f"[error] {raw}: {exc}", file=sys.stderr)
    return successes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download one or more Instagram Reels.")
    parser.add_argument("urls", nargs="+", help="Reel URLs or shortcodes")
    parser.add_argument(
        "-o",
        "--output",
        default="downloads/reels",
        help="Directory to store downloaded reels (default: downloads/reels)",
    )
    parser.add_argument("--username", help="Instagram username (only needed for private reels)")
    parser.add_argument("--password", help="Instagram password (omit to prompt securely)")
    parser.add_argument(
        "--sessionid",
        help="Instagram sessionid cookie value. Recommended for automation; bypasses interactive login.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    output_dir = Path(args.output).expanduser().resolve()

    successes = download_many(args.urls, output_dir, args.username, args.password, args.sessionid)
    if successes == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
