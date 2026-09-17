"""Reading whatever spreadsheet the team actually keeps.

    pytest test_ingest.py -v

Written against the shape of this team's own sheets rather than a tidy
invention: one workbook, a tab per person, headings carrying stray semicolons
and colons, a scratch tab with no heading row at the front, and an internal
"Audit Details" column that must not be mistaken for anything the matcher
wants.
"""
import io

import pandas as pd
import pytest

from app import ingest


# --------------------------------------------------------------------------- #
# The headings this team has used for years
# --------------------------------------------------------------------------- #

THEIRS = ["Date :", "Portals ;", "Company ;", "URL Links ;", "Positions ;",
          "Profile ;", "Audit Details", "VA Jobs", "Column 1", "Column 2"]


def test_the_headings_on_their_old_sheets_are_understood():
    mapping = ingest.auto_map(THEIRS)
    assert mapping["date"] == "Date :"
    assert mapping["platform"] == "Portals ;"
    assert mapping["company"] == "Company ;"
    assert mapping["url"] == "URL Links ;"
    assert mapping["title"] == "Positions ;"


def test_everything_else_on_those_sheets_is_left_blank():
    """The rest of the scheme has no column on these sheets and must stay empty.

    `Audit Details` is the one that used to be taken: it holds the name of
    whoever checked the row, and a loose "details" synonym filed it as the job's
    description link on every row of every sheet. `Profile` is a colleague's
    name, not a headline.
    """
    mapping = ingest.auto_map(THEIRS)
    assert mapping["description_url"] == ""
    assert mapping["headline"] == ""


@pytest.mark.parametrize("spelling", [
    "URL Links ;", "URL Link ;", "url links", "URL", "Links",
])
def test_the_link_column_however_it_is_spelt(spelling):
    assert ingest.auto_map(["Date", spelling, "Company"])["url"] == spelling


@pytest.mark.parametrize("spelling", ["Portals ;", "Portal", "portals", "Platform"])
def test_the_portal_column_however_it_is_spelt(spelling):
    assert ingest.auto_map(["Date", spelling, "Company"])["platform"] == spelling


@pytest.mark.parametrize("spelling", ["Positions ;", "Position", "positions", "Job Title"])
def test_the_position_column_however_it_is_spelt(spelling):
    assert ingest.auto_map([spelling, "Company", "Date"])["title"] == spelling


def test_an_exact_heading_beats_one_that_merely_starts_the_same():
    """"Positions" is the column; "Position Type" is full-time or contract."""
    mapping = ingest.auto_map(["Position Type", "Positions", "Company"])
    assert mapping["title"] == "Positions"


# --------------------------------------------------------------------------- #
# A workbook with a tab per person
# --------------------------------------------------------------------------- #

def workbook(tabs: dict) -> bytes:
    """`tabs` is {name: DataFrame}, written out as one .xlsx."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, frame in tabs.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return buf.getvalue()


def a_real_tab(n=5, first_job="Billing Specialist"):
    return pd.DataFrame({
        "Date :": ["06/30/2026"] * n,
        "Portals ;": ["Indeed."] * n,
        "Company ;": [f"Client {i}" for i in range(n)],
        "URL Links ;": [f"https://www.indeed.com/viewjob?jk=abc{i:013d}" for i in range(n)],
        "Positions ;": [first_job] + [f"Role {i}" for i in range(1, n)],
        "Audit Details": ["Fahad Hassan"] * n,
    })


def a_scratch_tab():
    """No heading row at all — the first job is sitting in row one.

    This is the front tab of the team's real workbook, and reading it as the
    sheet ate that first job as the column names.
    """
    return pd.DataFrame([
        ["Revenue Cycle Consultant", "Tria Federal", "Remote"],
        ["Accounts Receivable Clerk", "Optum", "Remote"],
    ], columns=["Accounting Coordinator", "Assist International",
                "https://www.indeed.com/viewjob?jk=7c484e2a51f6fa0a"])


def test_the_tab_with_the_work_wins_over_the_scratch_tab_in_front_of_it():
    content = workbook({"Sheet10": a_scratch_tab(), "Sehar batool.": a_real_tab()})
    frame = ingest.read_table(content, "Old Apply sheets.xlsx")
    assert frame.attrs["sheet"] == "Sehar batool."
    assert ingest.auto_map(list(frame.columns))["url"] == "URL Links ;"


def test_the_workbook_says_what_else_was_in_it():
    """So the screen can offer the others rather than leave it to be found out."""
    content = workbook({"Sheet10": a_scratch_tab(), "Faria": a_real_tab(),
                        "Hafsa": a_real_tab()})
    frame = ingest.read_table(content, "sheets.xlsx")
    assert frame.attrs["sheets"] == ["Sheet10", "Faria", "Hafsa"]


def test_a_named_tab_is_read_even_when_it_is_not_the_best_guess():
    content = workbook({"Sheet10": a_scratch_tab(), "Faria": a_real_tab(),
                        "Hafsa": a_real_tab(first_job="Prior Authorisation")})
    frame = ingest.read_table(content, "sheets.xlsx", sheet="Hafsa")
    assert frame.attrs["sheet"] == "Hafsa"
    assert frame["Positions ;"].iloc[0] == "Prior Authorisation"


def test_a_tab_named_with_a_stray_space_can_still_be_asked_for():
    """"Aleena " is a real tab on their workbook, and a form field trims."""
    content = workbook({"Sheet10": a_scratch_tab(), "Aleena ": a_real_tab()})
    frame = ingest.read_table(content, "sheets.xlsx", sheet="Aleena")
    assert frame.attrs["sheet"] == "Aleena "


def test_a_tab_that_is_not_there_says_so():
    content = workbook({"Faria": a_real_tab()})
    with pytest.raises(ValueError, match="no tab called"):
        ingest.read_table(content, "sheets.xlsx", sheet="Nobody")


def test_a_csv_is_still_just_a_csv():
    csv = b"Date,Portals ;,Company ;,URL Links ;,Positions ;\n" \
          b"06/30/2026,Indeed.,AOTI,https://www.indeed.com/viewjob?jk=a1b2c3d4e5f6,Biller\n"
    frame = ingest.read_table(csv, "sheet.csv")
    assert frame.attrs["sheet"] == ""
    assert frame.attrs["sheets"] == []
    mapping = ingest.auto_map(list(frame.columns))
    assert ingest.apply_mapping(frame.to_dict("records"), mapping)[0]["company"] == "AOTI"


def test_their_rows_come_through_the_whole_pipeline():
    content = workbook({"Sheet10": a_scratch_tab(), "Maimoona": a_real_tab(n=4)})
    frame = ingest.read_table(content, "Old Apply sheets.xlsx")
    rows = ingest.apply_mapping(frame.to_dict("records"),
                                ingest.auto_map(list(frame.columns)))
    assert len(rows) == 4
    first = rows[0]
    assert first["title"] == "Billing Specialist"
    assert first["company"] == "Client 0"
    assert first["platform"] == "Indeed."
    assert first["date"] == "06/30/2026"
    assert first["url"].startswith("https://www.indeed.com/viewjob")
    # The audit column belongs to nothing the matcher reads.
    assert first["description_url"] == ""
    assert first["headline"] == ""
