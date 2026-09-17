"""Turn whatever spreadsheet a BD hands you into rows the matcher understands."""
from __future__ import annotations

import io
import re

import pandas as pd

# The canonical fields the matcher needs. Everything else in the sheet is ignored.
# Headings are compared with punctuation and spacing stripped, so "URL Links ;"
# and "urllinks" are the same name. The plural forms this team's own sheets have
# carried for years — Portals, URL Links, Positions — are listed outright rather
# than left to the prefix rule to reach, so they win a tie against a column that
# merely starts with the same word.
FIELDS = [
    {"key": "url", "label": "Job link",
     "synonyms": ["url", "urls", "urllink", "urllinks", "link", "links", "joblink",
                  "joburl", "posting", "postlink", "href", "jobpost", "applylink"]},
    {"key": "title", "label": "Job title",
     "synonyms": ["title", "jobtitle", "position", "positions", "role", "roles", "job",
                  "projecttitle", "projectname", "post"]},
    {"key": "company", "label": "Company",
     "synonyms": ["company", "companies", "client", "clients", "employer", "org",
                  "organization", "buyer", "companyname", "clientname"]},
    {"key": "platform", "label": "Platform",
     "synonyms": ["platform", "platforms", "portal", "portals", "source", "sources",
                  "site", "board", "boards", "channel", "website", "websites", "medium"]},
    {"key": "date", "label": "Applied on",
     "synonyms": ["date", "dates", "applied", "appliedon", "applieddate", "appliedat",
                  "timestamp", "day", "applydate"]},
    {"key": "headline", "label": "Headline",
     "synonyms": ["headline", "specialty", "speciality", "category", "market"]},
    # Where the posting is written out, when that is not the apply link. Never
    # part of a fingerprint: two profiles can hold two different links to the
    # same job's description, and matching on it would split one posting in two.
    #
    # Named narrowly, and it has to stay that way. A bare "details" or "spec"
    # reached "Audit Details" — an internal column on every one of this team's
    # old sheets, holding the name of whoever checked the row — and filed a
    # colleague's name as the job's description link on a few thousand rows.
    {"key": "description_url", "label": "Job description link",
     "synonyms": ["descriptionurl", "description", "jobdescription", "jd", "jdlink",
                  "jdurl", "descriptionlink", "jobdetails", "jobdetailsurl",
                  "posting", "postingurl"]},
]

MAX_ROWS = 20000


def _slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _tidy(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.fillna("")
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame.loc[:, [c for c in frame.columns if c and not c.startswith("Unnamed")]]


def _looks_like_a_sheet(headers: list) -> int:
    """How many of the fields the matcher needs this tab's headings name."""
    mapping = auto_map([str(h).strip() for h in headers])
    return sum(1 for key in ("url", "title", "company", "platform", "date")
               if mapping.get(key))


def read_table(content: bytes, filename: str, sheet: object = None) -> pd.DataFrame:
    """Read csv, tsv, xls or xlsx into a string-typed dataframe.

    For a workbook, the tab that actually holds the work — not tab one.

    The sheets this team keeps are one workbook with a tab per person, and the
    first tab is a scratch pad with no heading row at all. Reading tab one meant
    a BD uploading their own workbook had their real sheet ignored and forty
    rows of somebody's notes read in its place, with the first job silently
    eaten as the column names. The tab whose headings name most of what the
    matcher needs wins; `sheet` overrides the guess when the person knows better.

    `frame.attrs` carries which tab was read and what else was on offer, so the
    screen can say so rather than leaving it to be found out downstream.
    """
    lower = filename.lower()
    names = []
    chosen = ""

    if lower.endswith((".csv", ".txt")):
        frame = _tidy(pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False,
                                  engine="python", on_bad_lines="skip"))
    elif lower.endswith(".tsv"):
        frame = _tidy(pd.read_csv(io.BytesIO(content), sep="	", dtype=str,
                                  keep_default_na=False, engine="python",
                                  on_bad_lines="skip"))
    elif lower.endswith((".xlsx", ".xlsm", ".xls")):
        engine = "openpyxl" if lower.endswith((".xlsx", ".xlsm")) else None
        book = pd.ExcelFile(io.BytesIO(content), engine=engine)
        names = list(book.sheet_names)
        if not names:
            raise ValueError("That workbook has no sheets in it.")

        wanted = str(sheet).strip() if sheet not in (None, "") else ""
        if wanted:
            # Matched on the trimmed name. Tab names carry stray spaces all the
            # time — "Aleena " is one of this team's — and a name that came back
            # from this very function has already been through a form field that
            # trims, so comparing raw would reject the tab it just offered.
            by_name = {name.strip(): name for name in names}
            if wanted not in by_name:
                raise ValueError("That workbook has no tab called %r." % wanted)
            chosen = by_name[wanted]
        else:
            # Scored on the heading row alone: one cheap read per tab, rather
            # than pulling a whole workbook into memory to choose between them.
            best = -1
            for name in names:
                peek = pd.read_excel(book, sheet_name=name, dtype=str, nrows=0)
                score = _looks_like_a_sheet(list(peek.columns))
                if score > best:
                    best, chosen = score, name
        frame = _tidy(pd.read_excel(book, sheet_name=chosen, dtype=str))
    else:
        raise ValueError("Upload a .csv, .tsv, .xls or .xlsx file.")

    if frame.empty:
        raise ValueError("The tab %r has no rows in it." % chosen if chosen
                         else "That sheet has no rows.")
    frame = frame.head(MAX_ROWS)
    frame.attrs["sheet"] = chosen
    frame.attrs["sheets"] = names
    return frame


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
