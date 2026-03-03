# JEE Main Cutoffs 2025 (JoSAA + CSAB)

This is a static website that displays official JoSAA and CSAB opening/closing rank data for 2025.

## Quick start

1. Install Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Fetch data:

```bash
python3 scripts/fetch_orcr.py --source josaa
python3 scripts/fetch_orcr.py --source csab
```

3. Open the site (any static server):

```bash
python3 -m http.server 8000
```

Then open `http://localhost:8000` in your browser.

## Notes

- The fetch script attempts to use `ALL` options to minimize requests.
- If the portal blocks bulk queries, rerun with `--no-prefer-all` and/or `--limit` to debug.
- Data files live in `data/` and are loaded by `app.js`.
