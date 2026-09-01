"""Turn whatever spreadsheet a BD hands you into rows the matcher understands."""
from __future__ import annotations

import io
import re

import pandas as pd

# The canonical fields the matcher needs. Everything else in the sheet is ignored.
FIELDS = [
    {"key": "url", "label": "Job link",
     "synonyms": ["url", "link", "joblink", "joburl", "posting", "postlink", "href", "jobpost", "applylink"]},
    {"key": "title", "label": "Job title",
     "synonyms": ["title", "jobtitle", "position", "role", "job", "projecttitle", "projectname", "post"]},
    {"key": "company", "label": "Client or company",
     "synonyms": ["company", "client", "employer", "org", "organization", "buyer", "companyname", "clientname"]},
    {"key": "platform", "label": "Platform",
     "synonyms": ["platform", "source", "site", "portal", "board", "channel", "website", "medium"]},
    {"key": "date", "label": "Applied on",
     "synonyms": ["date", "applied", "appliedon", "applieddate", "appliedat", "timestamp", "day", "applydate"]},
    # Where the posting is written out, when that is not the apply link. Never
    # part of a fingerprint: two profiles can hold two different links to the
    # same job's description, and matching on it would split one posting in two.
    {"key": "description_url", "label": "Job description link",
     "synonyms": ["descriptionurl", "description", "jobdescription", "jd", "jdlink",
                  "jdurl", "descriptionlink", "spec", "details", "detailsurl",
                  "jobdetails", "posting", "postingurl"]},
]

MAX_ROWS = 20000


def _slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def read_table(content: bytes, filename: str) -> pd.DataFrame:
    """Read csv, tsv, xls or xlsx into a string-typed dataframe."""
    lower = filename.lower()
    if lower.endswith((".csv", ".txt")):
        frame = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False,
                            engine="python", on_bad_lines="skip")
    elif lower.endswith(".tsv"):
        frame = pd.read_csv(io.BytesIO(content), sep="\t", dtype=str, keep_default_na=False,
                            engine="python", on_bad_lines="skip")
    elif lower.endswith((".xlsx", ".xlsm")):
        frame = pd.read_excel(io.BytesIO(content), dtype=str, engine="openpyxl")
    elif lower.endswith(".xls"):
        frame = pd.read_excel(io.BytesIO(content), dtype=str)
    else:
        raise ValueError("Upload a .csv, .tsv, .xls or .xlsx file.")

    frame = frame.fillna("")
    frame.columns = [str(column).strip() for column in frame.columns]
    frame = frame.loc[:, [c for c in frame.columns if c and not c.startswith("Unnamed")]]
    if frame.empty:
        raise ValueError("That sheet has no rows.")
    return frame.head(MAX_ROWS)


def auto_map(headers: list[str]) -> dict[str, str]:
    """Best-guess mapping from the sheet's own headers to canonical fields.

    Scored rather than first-match: an exact header name always beats a partial
    one, so a sheet with both "Client" and "Client Country" picks the right one.
    """
    mapping: dict[str, str] = {}
    claimed: set[str] = set()

    for field in FIELDS:
        best_header, best_score = "", 0
        for header in headers:
            if header in claimed:
                continue
            slug = _slug(header)
            if not slug:
                continue
            for synonym in field["synonyms"]:
                if slug == synonym:
                    score = 3
                elif slug.startswith(synonym) or slug.endswith(synonym):
                    score = 2
                elif synonym in slug:
                    score = 1
                else:
                    continue
                if score > best_score:
                    best_score, best_header = score, header
        mapping[field["key"]] = best_header
        if best_header:
            claimed.add(best_header)
    return mapping


def safe_url(value: object) -> str:
    """Keep http(s) and bare-host links, drop every other scheme.

    A job link ends up in an `href` on someone else's screen. A sheet is not a
    trusted document — one `javascript:` cell would otherwise run in the app's
    own origin the moment a colleague clicks "open" on their list.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    head = text.split("/", 1)[0]
    if ":" in head and head.split(":", 1)[0].lower() not in ("http", "https"):
        return ""
    return text


def project_rows(rows: list[dict], mapping: dict[str, str]) -> list[dict]:
    """Every row in canonical form, blanks and all.

    The hand-entry screen needs the half-filled rows too — a row someone is
    still typing has to survive a save, or it disappears under their cursor.
    """
    projected = []
    for row in rows:
        record = {}
        for field in FIELDS:
            source = mapping.get(field["key"]) or ""
            record[field["key"]] = str(row.get(source, "") or "").strip() if source else ""
        record["url"] = safe_url(record["url"])
        record["description_url"] = safe_url(record["description_url"])
        projected.append(record)
    return projected


def is_usable(record: dict) -> bool:
    """Enough to identify a job by link, or by client and title."""
    return bool(record["url"] or record["title"] or record["company"])


def apply_mapping(rows: list[dict], mapping: dict[str, str]) -> list[dict]:
    """Project raw sheet rows onto the canonical field names, dropping the
    rows that carry nothing the matcher could use."""
    return [record for record in project_rows(rows, mapping) if is_usable(record)]
