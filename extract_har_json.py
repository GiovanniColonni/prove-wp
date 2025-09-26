#!/usr/bin/env python3
"""
Extract JSON API responses from a HAR file and summarize backend-like calls.

Outputs:
- A CSV summary of likely backend API requests
- Pretty-printed JSON response bodies (when parseable)
- Pretty-printed JSON request bodies for write operations (when present)

Heuristics to identify backend/API calls:
- Response mimeType contains "json" OR path contains "/api/", "/v1/", "/v2/", "/graphql", "/wp-json/"
- Path ends with .json
- HTTP method is POST/PUT/PATCH/DELETE
- Response body appears to be JSON (starts with { or [ and parses)

Usage:
  python3 extract_har_json.py --input path/to/file.har --out output_directory
"""

import argparse
import base64
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sys
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse


def slugify(text: str, max_len: int = 60) -> str:
    """Create a safe slug for filenames from arbitrary text."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\-_.:/]", "-", text)
    text = re.sub(r"[-]+", "-", text)
    if len(text) > max_len:
        text = text[:max_len].rstrip("-_.:")
    return text or "untitled"


def ensure_dir(path: str) -> None:
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def get_entry_fields(entry: Dict[str, Any]) -> Tuple[str, str, str, int, Dict[str, Any]]:
    req = entry.get("request", {})
    res = entry.get("response", {})
    url = req.get("url") or ""
    method = req.get("method") or ""
    started = entry.get("startedDateTime") or ""
    status = int(res.get("status") or 0)
    content = res.get("content") or {}
    return method, url, started, status, content


def is_probable_api(entry: Dict[str, Any]) -> bool:
    req = entry.get("request", {})
    res = entry.get("response", {})
    url = req.get("url") or ""
    method = (req.get("method") or "").upper()
    content = res.get("content") or {}
    mime = (content.get("mimeType") or res.get("mimeType") or "").lower()

    parsed = urlparse(url)
    path = parsed.path or ""
    ext = os.path.splitext(path)[1].lower()
    ext_block = {
        ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
        ".woff", ".woff2", ".ttf", ".otf", ".map", ".mp4", ".webm", ".mp3",
        ".wav", ".ogg", ".pdf", ".zip", ".gz", ".br", ".webp", ".avif", ".heic",
        ".eot",
    }
    if ext in ext_block:
        return False

    if "json" in mime:
        return True
    if path.endswith(".json"):
        return True
    lowered_path = path.lower()
    if any(seg in lowered_path for seg in ["/api/", "/v1/", "/v2/", "/graphql", "/wp-json/"]):
        return True
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        return True

    # Fallback: JSON-looking response body
    text = content.get("text")
    if text:
        encoding = content.get("encoding")
        try:
            if encoding == "base64":
                text = base64.b64decode(text).decode("utf-8", errors="ignore")
            s = text.strip()
            if s.startswith("{") or s.startswith("["):
                return True
        except Exception:
            pass

    return False


def decode_body_text(content: Dict[str, Any]) -> Optional[str]:
    text = content.get("text")
    if text is None:
        return None
    encoding = content.get("encoding")
    try:
        if encoding == "base64":
            return base64.b64decode(text).decode("utf-8", errors="ignore")
        return str(text)
    except Exception:
        return None


def strip_json_hardening_prefix(s: str) -> str:
    prefixes = [
        ")]}',\n",
        ")]}',",
        "while(1);\n",
        "while(1);",
        "for(;;);\n",
        "for(;;);",
    ]
    s2 = s.lstrip()
    for p in prefixes:
        if s2.startswith(p):
            return s2[len(p):].lstrip()
    return s


def try_parse_json(text: Optional[str]) -> Tuple[Optional[Any], bool]:
    if not text:
        return None, False
    s = strip_json_hardening_prefix(text).strip()
    if not s:
        return None, False
    try:
        return json.loads(s), True
    except Exception:
        return None, False


def try_extract_request_json(entry: Dict[str, Any]) -> Tuple[Optional[Any], bool]:
    req = entry.get("request", {})
    post = req.get("postData") or {}
    mime = (post.get("mimeType") or "").lower()
    text = post.get("text")
    if not text:
        return None, False
    if "json" in mime:
        obj, ok = try_parse_json(text)
        if ok:
            return obj, True
    # For urlencoded, attempt key/value capture
    if "x-www-form-urlencoded" in mime:
        params = post.get("params")
        if isinstance(params, list):
            obj = {p.get("name"): p.get("value") for p in params if p.get("name")}
            return obj, True
    # Try best-effort JSON regardless of mime
    obj, ok = try_parse_json(text)
    return (obj, ok) if ok else (None, False)


def write_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract JSON API responses from HAR")
    parser.add_argument("--input", required=True, help="Path to HAR file")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--include-nonjson", action="store_true", help="Include API-like entries without JSON response in CSV")
    args = parser.parse_args()

    har_path = os.path.abspath(args.input)
    out_dir = os.path.abspath(args.out)
    ensure_dir(out_dir)
    responses_dir = os.path.join(out_dir, "responses")
    requests_dir = os.path.join(out_dir, "requests")
    ensure_dir(responses_dir)
    ensure_dir(requests_dir)

    if not os.path.isfile(har_path):
        print(f"HAR file not found: {har_path}", file=sys.stderr)
        return 2

    with open(har_path, "r", encoding="utf-8") as f:
        try:
            har = json.load(f)
        except Exception as e:
            print(f"Failed to parse HAR as JSON: {e}", file=sys.stderr)
            return 2

    entries = (((har or {}).get("log") or {}).get("entries") or [])
    if not entries:
        print("No entries found in HAR.")
        return 0

    summary_rows = []
    total_api = 0
    total_json_saved = 0
    total_req_json_saved = 0

    for idx, entry in enumerate(entries, start=1):
        try:
            method, url, started, status, content = get_entry_fields(entry)
            probable_api = is_probable_api(entry)
            if not probable_api and not args.include_nonjson:
                # Skip early if not API-like unless user wants all
                # Still try parse JSON to catch missed API cases
                pass

            # Attempt to parse response JSON
            response_text = decode_body_text(content) or ""
            response_obj, response_is_json = try_parse_json(response_text)

            # Decide whether to include in CSV
            include = False
            if probable_api and (response_is_json or args.include_nonjson):
                include = True
            elif response_is_json:
                include = True

            if not include:
                continue

            total_api += 1

            parsed = urlparse(url)
            host = parsed.hostname or "host"
            path = parsed.path or "/"
            safe_path = slugify(path.replace("/", "-"))
            stamp = ""
            if started:
                try:
                    dt_obj = dt.datetime.fromisoformat(started.replace("Z", "+00:00"))
                    stamp = dt_obj.strftime("%Y%m%dT%H%M%S")
                except Exception:
                    stamp = ""
            hash_src = f"{method}|{url}|{started}|{status}"
            short_hash = hashlib.sha1(hash_src.encode("utf-8")).hexdigest()[:8]
            base_name = f"{str(idx).zfill(5)}_{method}_{slugify(host)}_{safe_path}_{short_hash}"

            response_json_path = ""
            if response_is_json and response_obj is not None:
                response_json_path = os.path.join(responses_dir, base_name + ".response.json")
                write_json(response_json_path, response_obj)
                total_json_saved += 1

            req_obj, req_is_json = try_extract_request_json(entry)
            request_json_path = ""
            if req_is_json and req_obj is not None:
                request_json_path = os.path.join(requests_dir, base_name + ".request.json")
                write_json(request_json_path, req_obj)
                total_req_json_saved += 1

            row = {
                "index": idx,
                "startedDateTime": started,
                "method": method,
                "url": url,
                "status": status,
                "response_mimeType": (content.get("mimeType") or ""),
                "is_probable_api": probable_api,
                "response_is_json": response_is_json,
                "response_json_file": response_json_path,
                "request_is_json": req_is_json,
                "request_json_file": request_json_path,
            }
            summary_rows.append(row)

        except Exception as e:
            # Continue with best effort on unexpected entry shapes
            print(f"Warning: failed to process entry {idx}: {e}")
            continue

    summary_path = os.path.join(out_dir, "api_calls_summary.csv")
    with open(summary_path, "w", newline="", encoding="utf-8") as fcsv:
        writer = csv.DictWriter(
            fcsv,
            fieldnames=[
                "index",
                "startedDateTime",
                "method",
                "url",
                "status",
                "response_mimeType",
                "is_probable_api",
                "response_is_json",
                "response_json_file",
                "request_is_json",
                "request_json_file",
            ],
        )
        writer.writeheader()
        for row in summary_rows:
            writer.writerow(row)

    print(
        (
            f"Processed {len(entries)} entries. Included {len(summary_rows)} API-like calls.\n"
            f"Saved {total_json_saved} response JSON files and {total_req_json_saved} request JSON files.\n"
            f"Summary: {summary_path}\nResponses dir: {responses_dir}\nRequests dir: {requests_dir}"
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())


