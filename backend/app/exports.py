"""Excel output. Column widths and a frozen header row, because these sheets
get opened on a phone as often as a laptop.
"""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill("solid", fgColor="14202C")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
WIDTHS = {"#": 5, "Job title": 46, "Company": 26, "Client": 26, "Platform": 14, "Job link": 52,
          "Already tried by": 22, "Match ref": 30, "Metric": 34, "Value": 14,
          "BD": 20, "Applied by": 30, "People": 9, "Status": 12,
          "Found by": 24, "Found on": 18, "Description link": 46,
          "When · ET": 18, "Applied as": 20, "Developer": 20, "Role": 40,
          "Client email": 46, "Client": 30, "Status": 22, "Own jobs": 11,
          "Others' jobs": 13, "Found twice": 12, "Profiles": 30, "BDs": 24,
          "Developers": 24, "Furthest round": 18, "Open assessments": 11,
          "Next in the diary": 26, "Last activity": 15, "First approached": 17,
          "Round": 22, "Follows": 20, "Reported": 26, "Brief": 50, "Debrief": 50,
          "Deadline · ET": 18, "Set by": 20, "What": 40,
          "Round": 16, "Outcome": 12, "Follows": 18, "Reported by": 20,
          "What": 40, "Due · ET": 18, "Set by": 20, "Submitted": 18,
          "Submission": 46, "Notes": 60, "Applied on": 18}


# Excel treats a leading =, +, - or @ as the start of a formula. These sheets
# are built from cells somebody typed into their own spreadsheet, then opened by
# a colleague — so a title of `=cmd|'/c calc'!A1` would execute on their machine,
# not ours. A leading apostrophe tells Excel "this is text", and is not shown.
_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value):
    if isinstance(value, str) and value.startswith(_FORMULA_LEAD):
        return "'" + value
    return value


def _write_sheet(book: Workbook, title: str, columns: list[str], rows: list[list]) -> None:
    sheet = book.create_sheet(title[:31] or "Sheet")
    sheet.append(columns)
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center")
    for row in rows:
        sheet.append([_safe_cell(value) for value in row])
    for index, column in enumerate(columns, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = WIDTHS.get(column, 18)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions


def assignment_workbook(person: str, jobs: list[dict]) -> bytes:
    """One profile's list, as the file people actually work from.

    Carries `Found by` and the description link, because the download is what
    somebody works through on a train and it should not be a worse document
    than the screen it came from. Knowing a run of jobs all came off one
    colleague's search is what tells you whether to trust the next twenty.
    """
    book = Workbook()
    book.remove(book.active)
    columns = ["#", "Job title", "Company", "Found by", "Found on", "Platform",
               "Job link", "Description link", "Status"]
    rows = [
        [i, j.get("title", ""), j.get("company", ""),
         ", ".join(j.get("found_by") or []), j.get("found_on", ""),
         j.get("platform", ""),
         j.get("url", ""), j.get("description_url", ""), j.get("status", "pending")]
        for i, j in enumerate(jobs, start=1)
    ]
    _write_sheet(book, f"{person} jobs", columns, rows)
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def client_workbook(clients: list[dict], details: list[dict]) -> bytes:
    """Every client, every conversation and every test, as three sheets.

    The same three cuts the screen shows, in the order somebody reads them: who
    the clients are, what was said, and what is owed. A conversation carries the
    round it is and the round it followed, because a client who ran four rounds
    before saying no is a different fact from four clients who each said no
    once, and a flat list cannot tell them apart.
    """
    book = Workbook()
    book.remove(book.active)

    _write_sheet(
        book, "Clients",
        ["Client", "Status", "Applied", "Own jobs", "Others' jobs",
         "Found twice", "Profiles", "BDs", "Developers", "Furthest round",
         "Open assessments", "Next in the diary", "First approached", "Last activity"],
        [[row["client"], row["status_label"], row["applications"], row["own_jobs"],
          row["others_jobs"], row["found_twice"], ", ".join(row["profiles"]),
          ", ".join(row["bds"]), ", ".join(row["developers"]),
          row["furthest"] or "", row["open_tests"],
          (row["next_up"] or {}).get("when", {}).get("label", ""),
          row["first_seen"] or "", row["last_activity"] or ""]
         for row in clients])

    talks = []
    for detail in details:
        client = detail["client"]["client"]
        for block in detail["conversations"]:
            for row in block["rounds"]:
                talks.append([
                    client, row["when"]["label"], row["profile"],
                    row.get("developer") or "", row["role"],
                    f"{row['round']} of {row['rounds']} · {row['stage']}"
                    if row.get("rounds", 1) > 1 else row["stage"],
                    (row["follows"]["stage"] if row.get("follows") else ""),
                    row["status"], row["outcome"],
                    f"{row['reported_by']} · {row['reported_at']}"
                    if row.get("reported_by") else "",
                    (row["job"] or {}).get("url", ""), row.get("email_url", ""),
                    row.get("notes", ""), row.get("debrief", "")])
    _write_sheet(
        book, "Conversations",
        ["Client", "When · ET", "Applied as", "Developer", "Role", "Round",
         "Follows", "Status", "Outcome", "Reported", "Job link", "Client email",
         "Brief", "Debrief"],
        talks)

    tests = []
    for detail in details:
        client = detail["client"]["client"]
        for row in detail["tests"]:
            tests.append([
                client, row["title"], row["profile"], row.get("developer") or "",
                (row["due"]["label"] if row.get("due") else "none set"),
                f"{row['status']} · overdue" if row["overdue"] else row["status"],
                row.get("set_by") or "",
                (row["submitted"]["label"] if row.get("submitted") else ""),
                row["submission_url"], row.get("email_url", "")])
    _write_sheet(
        book, "Assessments",
        ["Client", "What", "Applied as", "Developer", "Deadline · ET", "Status",
         "Set by", "Submitted", "Submission", "Client email"],
        tests)

    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def pipeline_workbook(interviews: list[dict], assessments: list[dict]) -> bytes:
    """Every conversation and every take-home, in one file.

    The half of this product that has no export at all until now. Everything
    downloadable so far counts what went out — rows, lists, duplication — and a
    team can improve all of it without winning a single piece of work. This is
    the other half, and it is the part somebody wants in a spreadsheet when
    they are asked what the last quarter actually produced.

    Times are the team's clock, said so in the column heading, because a
    spreadsheet has no tooltip to explain itself later.
    """
    book = Workbook()
    book.remove(book.active)

    _write_sheet(
        book, "Conversations",
        ["When · ET", "Applied as", "Developer", "Company", "Role", "Round",
         "Follows", "How", "Status", "Outcome", "Reported by", "Job link",
         "Client email"],
        [[row["when"]["label"], row["profile"], row.get("developer") or "",
          row["client"], row["role"],
          f"{row['round']} of {row['rounds']} · {row['stage']}"
          if row.get("rounds", 1) > 1 else row["stage"],
          (row["follows"]["stage"] if row.get("follows") else ""),
          row["mode"], row["status"], row["outcome"],
          row.get("reported_by") or "",
          (row["job"] or {}).get("url", ""),
          row.get("email_url", "")]
         for row in interviews])

    _write_sheet(
        book, "Assessments",
        ["What", "Company", "Applied as", "Developer", "Due · ET", "Status",
         "Set by", "Submitted", "Submission", "Job link", "Client email",
         "Applied on", "Notes"],
        [[row["title"], row["client"], row["profile"], row.get("developer") or "",
          (row["due"]["label"] if row.get("due") else "none set"),
          # Said in words rather than left as a status somebody has to know how
          # to read. A file outlives the screen that explains it.
          f"{row['status']} · overdue" if row["overdue"] else row["status"],
          row.get("set_by") or "",
          (row["submitted"]["label"] if row.get("submitted") else ""),
          row["submission_url"],
          # The posting, on the same terms as the Conversations sheet. A
          # spreadsheet that describes one conversation two different ways is
          # the thing this whole payload is trying not to be.
          (row["job"] or {}).get("url", ""),
          row.get("email_url", ""),
          (row["job"] or {}).get("applied_on", ""),
          row["notes"]]
         for row in assessments])

    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def report_workbook(report: dict, per_person: dict[str, list[dict]],
                    collisions: list[dict], matrix_names: list[str],
                    matrix: list[list[int]],
                    turned_down: list[dict] | None = None) -> bytes:
    book = Workbook()
    book.remove(book.active)

    _write_sheet(book, "Summary", ["Metric", "Value"],
                 [[k, v] for k, v in report.items()])

    _write_sheet(book, "Collisions",
                 ["Job title", "Company", "Platform", "Job link", "Applied by", "People"],
                 [[c["title"], c["company"], c["platform"], c["url"],
                   ", ".join(c["applied_by"]), len(c["applied_by"])] for c in collisions])

    _write_sheet(book, "Overlap matrix", ["BD"] + matrix_names,
                 [[matrix_names[i]] + row for i, row in enumerate(matrix)])

    # What was turned down and why. On the screen already; without it here the
    # download is a worse document than the page it came from, and this is the
    # sheet a manager reads away from their desk.
    if turned_down:
        _write_sheet(book, "Skipped",
                     ["Job title", "Company", "Profile", "Reason", "When", "Job link"],
                     [[t.get("title", ""), t.get("company", ""), t.get("profile", ""),
                       t.get("reason", ""), t.get("when", ""), t.get("url", "")]
                      for t in turned_down])

    for person, jobs in per_person.items():
        _write_sheet(book, person, ["#", "Job title", "Company", "Platform", "Job link"],
                     [[i, j.get("title", ""), j.get("company", ""),
                       j.get("platform", ""), j.get("url", "")]
                      for i, j in enumerate(jobs, start=1)])

    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()
