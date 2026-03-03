#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional
import re

import requests
from bs4 import BeautifulSoup

USER_AGENT = "jee-cutoffs-bot/1.0 (+https://github.com/)"

SELECT_KEYWORDS = {
    "round": ["round"],
    "institute_type": ["institute type", "institutetype", "inst type"],
    "institute": ["institute name", "institute"],
    "program": ["academic program", "program"],
    "seat_type": ["seat type", "seat type / category", "seat type/category", "category"],
}

HEADER_MAP = {
    "round": ["round"],
    "institute_type": ["institute type"],
    "institute": ["institute", "institute name"],
    "program": ["academic program", "program"],
    "seat_type": ["seat type", "seat type / category", "category"],
    "quota": ["quota"],
    "gender": ["gender", "gender-neutral", "gender neutral"],
    "opening_rank": ["opening rank", "opening"],
    "closing_rank": ["closing rank", "closing"],
}

@dataclass
class SelectInfo:
    name: str
    label: str
    options: List[Dict[str, str]]
    selected: str

@dataclass
class FormState:
    hidden: Dict[str, str]
    selects: Dict[str, SelectInfo]
    all_selects: List[SelectInfo]
    submit_name: Optional[str]
    submit_value: Optional[str]
    submit_target: Optional[str]


def clean_text(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split()).strip()


def find_label_text(select):
    if not select:
        return ""
    select_id = select.get("id")
    label_text = ""
    if select_id:
        label = select.find_parent().find("label", attrs={"for": select_id}) if select.find_parent() else None
        if label:
            label_text = clean_text(label.get_text())
    if not label_text:
        prev = select.find_previous("label")
        if prev:
            label_text = clean_text(prev.get_text())
    if not label_text:
        parent = select.find_parent()
        if parent:
            text = clean_text(parent.get_text(" "))
            label_text = text.split(" ")[0] if text else ""
    return label_text


def parse_select(select) -> Optional[SelectInfo]:
    name = select.get("name") or select.get("id")
    if not name:
        return None
    label = find_label_text(select) or name
    options = []
    selected = ""
    for option in select.find_all("option"):
        value = option.get("value", "").strip()
        text = clean_text(option.get_text())
        options.append({"value": value, "text": text})
        if "selected" in option.attrs:
            selected = value
    if not selected and options:
        selected = options[0]["value"]
    return SelectInfo(name=name, label=label, options=options, selected=selected)


def identify_selects(selects: List[SelectInfo]) -> Dict[str, SelectInfo]:
    mapped: Dict[str, SelectInfo] = {}
    for sel in selects:
        label = sel.label.lower()
        name = sel.name.lower()
        for key, keywords in SELECT_KEYWORDS.items():
            for kw in keywords:
                if kw in label or kw in name:
                    mapped[key] = sel
                    break
            if key in mapped:
                break
    # Fallback: if labels are missing or unhelpful, map by position.
    if len(mapped) < len(SELECT_KEYWORDS):
        order = list(SELECT_KEYWORDS.keys())
        for idx, sel in enumerate(selects):
            if idx >= len(order):
                break
            key = order[idx]
            if key not in mapped:
                mapped[key] = sel
    return mapped


def extract_form_state(html: str) -> FormState:
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form") or soup

    hidden = {}
    for inp in form.find_all("input", attrs={"type": "hidden"}):
        name = inp.get("name")
        if name:
            hidden[name] = inp.get("value", "")

    selects: List[SelectInfo] = []
    for sel in form.find_all("select"):
        parsed = parse_select(sel)
        if parsed:
            selects.append(parsed)

    submit_name = None
    submit_value = None
    submit_target = None
    submit = form.find("input", attrs={"type": "submit"}) or form.find("button", attrs={"type": "submit"})
    if submit:
        submit_name = submit.get("name") or submit.get("id")
        submit_value = submit.get("value") or submit.get_text(strip=True) or "Submit"
    else:
        # ASP.NET often uses __doPostBack on buttons.
        for btn in form.find_all(["input", "button"]):
            onclick = btn.get("onclick", "")
            match = re.search(r"__doPostBack\\('([^']+)'", onclick)
            if match:
                submit_target = match.group(1)
                submit_name = match.group(1)
                submit_value = btn.get("value") or btn.get_text(strip=True) or ""
                break

    mapped_selects = identify_selects(selects)
    return FormState(
        hidden=hidden,
        selects=mapped_selects,
        all_selects=selects,
        submit_name=submit_name,
        submit_value=submit_value,
        submit_target=submit_target,
    )


def pick_all_or_first(options: List[Dict[str, str]], prefer_all: bool) -> List[Dict[str, str]]:
    if not options:
        return []
    if prefer_all:
        for opt in options:
            if opt["text"].strip().upper() == "ALL":
                return [opt]
    return [opt for opt in options if opt["text"] and "select" not in opt["text"].lower()]


def find_option(options: List[Dict[str, str]], target: str) -> Optional[Dict[str, str]]:
    target_lower = target.lower()
    for opt in options:
        if opt["value"].lower() == target_lower or opt["text"].lower() == target_lower:
            return opt
    for opt in options:
        if target_lower in opt["text"].lower():
            return opt
    return None


def postback(session: requests.Session, url: str, state: FormState, selections: Dict[str, str], target_name: str, target_value: str):
    data = dict(state.hidden)
    data.update(selections)
    data[target_name] = target_value
    data["__EVENTTARGET"] = target_name
    data["__EVENTARGUMENT"] = ""
    response = session.post(url, data=data)
    response.raise_for_status()
    return extract_form_state(response.text), response.text


def submit_form(session: requests.Session, url: str, state: FormState, selections: Dict[str, str]):
    data = dict(state.hidden)
    data.update(selections)
    data["__EVENTTARGET"] = state.submit_target or ""
    data["__EVENTARGUMENT"] = ""
    if state.submit_name:
        data[state.submit_name] = state.submit_value or "Submit"
    response = session.post(url, data=data)
    response.raise_for_status()
    return response.text


def pick_result_table(soup: BeautifulSoup):
    best = None
    best_score = -1
    for table in soup.find_all("table"):
        headers = [clean_text(th.get_text()) for th in table.find_all("th")]
        score = 0
        header_text = " ".join(headers).lower()
        if "opening" in header_text and "closing" in header_text:
            score += 3
        if "institute" in header_text:
            score += 2
        if table.find("tr"):
            score += len(table.find_all("tr"))
        if score > best_score:
            best = table
            best_score = score
    return best


def map_headers(headers: List[str]) -> Dict[int, str]:
    mapping = {}
    for idx, header in enumerate(headers):
        h = header.lower()
        for key, keywords in HEADER_MAP.items():
            for kw in keywords:
                if kw in h:
                    mapping[idx] = key
                    break
            if idx in mapping:
                break
    return mapping


def extract_rows(html: str, fallback: Dict[str, str]) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    table = pick_result_table(soup)
    if not table:
        return []

    header_cells = table.find_all("th")
    if header_cells:
        headers = [clean_text(th.get_text()) for th in header_cells]
    else:
        first_row = table.find("tr")
        headers = [clean_text(td.get_text()) for td in first_row.find_all("td")] if first_row else []

    header_map = map_headers(headers)

    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        row = dict(fallback)
        for idx, cell in enumerate(cells):
            key = header_map.get(idx)
            if not key:
                continue
            row[key] = clean_text(cell.get_text())
        rows.append(row)
    return rows


def run_fetch(
    url: str,
    out_path: str,
    prefer_all: bool,
    rounds: Optional[List[str]],
    limit: Optional[int],
    pause: float,
    debug: bool,
    dump_html: bool,
):
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    initial = session.get(url)
    initial.raise_for_status()

    state = extract_form_state(initial.text)
    if debug:
        print("Detected selects:")
        for sel in state.all_selects:
            print(f"- {sel.name} | label={sel.label!r} | options={len(sel.options)}")
        print("Mapped selects:")
        for key, sel in state.selects.items():
            print(f"  {key}: {sel.name}")
    if dump_html:
        Path("debug").mkdir(exist_ok=True)
        Path("debug/initial.html").write_text(initial.text, encoding="utf-8")
    selects = state.selects

    round_select = selects.get("round")
    inst_type_select = selects.get("institute_type")
    inst_select = selects.get("institute")
    program_select = selects.get("program")
    seat_select = selects.get("seat_type")

    if debug:
        missing = [k for k in ["round", "institute_type", "institute", "program", "seat_type"] if k not in selects]
        if missing:
            print(f"Warning: missing mapped selects: {', '.join(missing)}")

    rounds_options = round_select.options if round_select else []
    rounds_to_use = pick_all_or_first(rounds_options, prefer_all=False)
    if rounds:
        filtered = []
        for r in rounds:
            opt = find_option(rounds_options, r)
            if opt:
                filtered.append(opt)
        rounds_to_use = filtered

    if not rounds_to_use and round_select:
        rounds_to_use = pick_all_or_first(rounds_options, prefer_all=False)

    all_rows = []
    requests_count = 0

    for round_opt in rounds_to_use or [{"value": "", "text": ""}]:
        selections = {}
        if round_select:
            selections[round_select.name] = round_opt["value"]
            state, html = postback(session, url, state, selections, round_select.name, round_opt["value"])
            selects = state.selects
            inst_type_select = selects.get("institute_type")
            inst_select = selects.get("institute")
            program_select = selects.get("program")
            seat_select = selects.get("seat_type")
            if debug:
                print(f"After round {round_opt['text']!r}: inst_type options={len(inst_type_select.options) if inst_type_select else 0}")
            if dump_html:
                Path("debug/after_round.html").write_text(html, encoding="utf-8")
            time.sleep(pause)

        inst_types = pick_all_or_first(inst_type_select.options, prefer_all) if inst_type_select else [{"value": "", "text": ""}]
        for inst_type_opt in inst_types:
            if inst_type_select:
                selections[inst_type_select.name] = inst_type_opt["value"]
                state, html = postback(session, url, state, selections, inst_type_select.name, inst_type_opt["value"])
                selects = state.selects
                inst_select = selects.get("institute")
                program_select = selects.get("program")
                seat_select = selects.get("seat_type")
                if debug:
                    print(f"After inst type {inst_type_opt['text']!r}: inst options={len(inst_select.options) if inst_select else 0}")
                if dump_html:
                    Path("debug/after_inst_type.html").write_text(html, encoding="utf-8")
                time.sleep(pause)

            insts = pick_all_or_first(inst_select.options, prefer_all) if inst_select else [{"value": "", "text": ""}]
            for inst_opt in insts:
                if inst_select:
                    selections[inst_select.name] = inst_opt["value"]
                    state, html = postback(session, url, state, selections, inst_select.name, inst_opt["value"])
                    selects = state.selects
                    program_select = selects.get("program")
                    seat_select = selects.get("seat_type")
                    if debug:
                        print(f"After inst {inst_opt['text']!r}: program options={len(program_select.options) if program_select else 0}")
                    if dump_html:
                        Path("debug/after_inst.html").write_text(html, encoding="utf-8")
                    time.sleep(pause)

                programs = pick_all_or_first(program_select.options, prefer_all) if program_select else [{"value": "", "text": ""}]
                for prog_opt in programs:
                    if program_select:
                        selections[program_select.name] = prog_opt["value"]
                        state, html = postback(session, url, state, selections, program_select.name, prog_opt["value"])
                        selects = state.selects
                        seat_select = selects.get("seat_type")
                        if debug:
                            print(f"After program {prog_opt['text']!r}: seat options={len(seat_select.options) if seat_select else 0}")
                        if dump_html:
                            Path("debug/after_program.html").write_text(html, encoding="utf-8")
                        time.sleep(pause)

                    seats = pick_all_or_first(seat_select.options, prefer_all) if seat_select else [{"value": "", "text": ""}]
                    for seat_opt in seats:
                        if seat_select:
                            selections[seat_select.name] = seat_opt["value"]

                        fallback = {
                            "round": round_opt["text"],
                            "institute_type": inst_type_opt["text"],
                            "institute": inst_opt["text"],
                            "program": prog_opt["text"],
                            "seat_type": seat_opt["text"],
                        }

                        html = submit_form(session, url, state, selections)
                        if dump_html:
                            Path("debug/last_submit.html").write_text(html, encoding="utf-8")
                        rows = extract_rows(html, fallback)
                        all_rows.extend(rows)
                        requests_count += 1

                        print(f"Fetched {len(rows)} rows (total {len(all_rows)}).")
                        time.sleep(pause)

                        if limit and requests_count >= limit:
                            print("Reached request limit.")
                            break
                    if limit and requests_count >= limit:
                        break
                if limit and requests_count >= limit:
                    break
            if limit and requests_count >= limit:
                break

    meta = {
        "source": url,
        "year": 2025,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "notes": "Generated via fetch_orcr.py",
    }

    output = {"meta": meta, "rows": all_rows}
    out_file = Path(out_path)
    if not out_file.is_absolute():
        out_file = (Path(__file__).resolve().parent / out_file).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=True, indent=2)

    print(f"Saved {len(all_rows)} rows to {out_file}.")


def main():
    parser = argparse.ArgumentParser(description="Fetch JoSAA/CSAB OR-CR data into JSON.")
    parser.add_argument("--source", choices=["josaa", "csab"], required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--rounds", nargs="*", default=None, help="Round numbers or names to fetch")
    parser.add_argument("--prefer-all", action="store_true", default=True)
    parser.add_argument("--no-prefer-all", dest="prefer_all", action="store_false")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of submit requests (testing)")
    parser.add_argument("--pause", type=float, default=0.6, help="Seconds to pause between requests")
    parser.add_argument("--debug", action="store_true", help="Print form/select debug info")
    parser.add_argument("--dump-html", action="store_true", help="Dump form HTML snapshots into ./debug")
    args = parser.parse_args()

    if args.source == "josaa":
        url = "https://josaa.admissions.nic.in/applicant/SeatAllotmentResult/CurrentORCR.aspx"
        out = args.out or "../data/josaa-2025.json"
    else:
        url = "https://admissions.nic.in/csabspl/Applicant/SeatAllotmentResult/CurrentORCR.aspx"
        out = args.out or "../data/csab-2025.json"

    run_fetch(url, out, args.prefer_all, args.rounds, args.limit, args.pause, args.debug, args.dump_html)


if __name__ == "__main__":
    main()
