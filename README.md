# parv

Utility scripts and data for personal experiments.

## Instagram Reel downloader

Automate downloading Instagram Reels (public or accessible private reels) with the included Python helper script.

1. Install dependencies
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Download one or more reels
   ```bash
   # Public reels (no login)
   python instagram_reel_downloader.py https://www.instagram.com/reel/<shortcode>/ -o downloads/reels

   # Private reels (use a session cookie or credentials)
   python instagram_reel_downloader.py https://www.instagram.com/reel/<shortcode>/ --sessionid <your_sessionid>
   # or
   python instagram_reel_downloader.py https://www.instagram.com/reel/<shortcode>/ --username <user> --password <pass>
   ```

The script saves each reel inside `downloads/reels/<shortcode>/` with the video file named after the shortcode. Use a browser export (Developer Tools → Application → Cookies) to get a valid `sessionid` for private reels. Respect Instagram's Terms of Use when automating downloads.

## JEE Main Cutoffs 2025

The `jee-cutoffs-2025/` folder contains a static site and data fetcher for JoSAA/CSAB opening-closing ranks. See its README for details.
