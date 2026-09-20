"""Loading survey data from a local file, an upload, or a Google Drive / Sheets link."""
from __future__ import annotations

import io
from pathlib import Path
import re
import time

import httpx
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

SHEETS_ID = re.compile(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)")
DRIVE_ID = re.compile(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?id=)([a-zA-Z0-9-_]+)")


def drive_link_to_download_url(link: str) -> str:
    """Turn any Google Sheets / Drive share link into a direct xlsx download URL.

    The file must be shared as 'Anyone with the link'. Private files need OAuth,
    which this dashboard deliberately does not handle.
    """
    link = link.strip()
    m = SHEETS_ID.search(link)
    if m:
        return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=xlsx"
    m = DRIVE_ID.search(link)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    if link.startswith("http"):
        return link
    raise ValueError("Not a recognisable Google Sheets or Drive link.")


def read_bytes(raw: bytes, filename: str = "") -> pd.DataFrame:
    """Parse xlsx / xls / csv bytes into a DataFrame."""
    name = filename.lower()
    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(raw))
    if name.endswith(".xls"):
        return pd.read_excel(io.BytesIO(raw), engine="xlrd")
    try:
        return pd.read_excel(io.BytesIO(raw))
    except Exception:
        return pd.read_csv(io.BytesIO(raw))


def read_path(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    return read_bytes(path.read_bytes(), path.name)


async def read_link(link: str) -> pd.DataFrame:
    url = drive_link_to_download_url(link)
    sep = "&" if "?" in url else "?"
    url_with_cb = f"{url}{sep}_cb={int(time.time())}"
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        resp = await client.get(url_with_cb, headers=headers)
        resp.raise_for_status()
    if b"<html" in resp.content[:400].lower():
        raise ValueError(
            "The link returned an HTML page, not a file. Set sharing to "
            "'Anyone with the link' and try again."
        )
    return read_bytes(resp.content, url)



def default_dataframe() -> tuple[pd.DataFrame, str] | tuple[None, None]:
    """Pick up the first spreadsheet sitting in data/ on startup, if any."""
    for pattern in ("*.xlsx", "*.xls", "*.csv"):
        for f in sorted(DATA_DIR.glob(pattern)):
            return read_path(f), f.name
    return None, None
