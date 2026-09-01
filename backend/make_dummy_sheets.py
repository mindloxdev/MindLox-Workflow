"""Generate a fresh set of test sheets with a known, hand-checkable overlap.

    python make_dummy_sheets.py            # writes ../dummy_sheets/
    python make_dummy_sheets.py --out foo  # somewhere else

The catalogue is 85 jobs. Who claims what:

    Khuram   jobs  1-35
    Zahid    jobs 26-70     (shares 26-35 with Khuram — ten jobs)
    Nadia    jobs 61-85     (shares 61-70 with Zahid — ten jobs)

Nobody shares a job with all three, so every job can still go to somebody.
Each sheet is deliberately awkward in a different way:

    Khuram  tidy columns, but three rows are jobs already on his own sheet
            written with a different link format
    Zahid   different column names and order, every link carrying a newsletter
            tracking tail — must still match Khuram's clean links
    Nadia   messy headers, blank links on some rows, shouty titles
"""
from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

CLIENTS = [
    "Northwind Digital", "Ravensberg GmbH", "Bluepeak Studio", "Talloak Systems",
    "Verdant Labs", "Kite & Compass", "Orchard Retail Pvt Ltd", "Sable Analytics",
    "Copperline Media", "Harbourstone LLC", "Fernwood Health", "Quillmark Inc",
    "Alderpoint AI", "Mistvale Robotics", "Cobalt & Fern", "Larkspur Data",
    "Ironbridge Systems", "Marlowe & Sons", "Pinehaven Tech", "Solstice Retail",
    "Brambleton Media", "Whitcombe Legal", "Aster Bioscience", "Redmoor Logistics",
]

ROLES = [
    "LLM Fine-tuning Engineer", "RAG Pipeline Developer", "Computer Vision Engineer",
    "MLOps Engineer (AWS SageMaker)", "Chatbot Developer - OpenAI API",
    "Document AI / OCR Specialist", "Recommendation System Engineer",
    "Speech-to-Text Integration", "Data Scraping Automation",
    "Python Automation Scripts", "LangChain Agent Developer",
    "Vector Database Consultant", "Prompt Engineer for SaaS Product",
    "Fraud Detection Model Developer", "Time Series Forecasting Expert",
    "Senior React Developer", "Django Backend Developer", "Next.js Landing Page Build",
    "Shopify Theme Customisation", "WordPress Site Migration",
]

PLATFORMS = ["Upwork", "LinkedIn", "Indeed", "Freelancer"]


def build_url(platform: str, n: int) -> str:
    if platform == "Upwork":
        return f"https://www.upwork.com/jobs/~01{0xa1b2c30000 + n * 7717:016x}"
    if platform == "LinkedIn":
        return f"https://www.linkedin.com/jobs/view/{3941200000 + n * 137}"
    if platform == "Indeed":
        return f"https://pk.indeed.com/viewjob?jk={0xf40e900000 + n * 5501:016x}&from=serp"
    slug = ROLES[n % len(ROLES)].lower().replace(" ", "-").replace("/", "")
    return f"https://www.freelancer.com/projects/machine-learning/{slug}-{7300000 + n}"


def job(n: int) -> dict:
    platform = PLATFORMS[n % len(PLATFORMS)]
    return {
        "n": n,
        "title": ROLES[n % len(ROLES)],
        "company": CLIENTS[n % len(CLIENTS)],
        "platform": platform,
        "url": build_url(platform, n),
        "date": f"2026-08-{(n % 27) + 1:02d}",
    }


def scruffy(url: str) -> str:
    """The same link as somebody else would have pasted it."""
    return url.replace("https://www.", "http://").replace("https://", "http://")


def write(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"  {path.name:24s} {len(rows):3d} rows")


def main(out: str) -> None:
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    random.seed(11)

    # ---- Khuram: tidy, plus three self-duplicates written differently -------
    jobs = [job(n) for n in range(1, 36)]
    rows = [[j["title"], j["company"], j["platform"], j["url"], j["date"]] for j in jobs]
    for j in (jobs[4], jobs[17], jobs[29]):
        rows.append([j["title"], j["company"], j["platform"], scruffy(j["url"]), j["date"]])
    random.shuffle(rows)
    write(folder / "khuram-applied.csv",
          ["Job Title", "Company", "Platform", "Job URL", "Applied On"], rows)

    # ---- Zahid: different headers and order, tracking tail on every link ----
    jobs = [job(n) for n in range(26, 71)]
    rows = [[j["date"], j["title"], j["company"], j["platform"],
             j["url"] + "?utm_source=newsletter&ref=digest"] for j in jobs]
    write(folder / "zahid-applied.csv",
          ["Date", "Position", "Client", "Source", "Link"], rows)

    # ---- Nadia: messy headers, some links missing, some titles shouting ----
    jobs = [job(n) for n in range(61, 86)]
    rows = []
    for i, j in enumerate(jobs, start=1):
        link = "" if i % 4 == 0 else j["url"]
        title = j["title"].upper() if i % 3 == 0 else j["title"]
        rows.append([i, title, j["company"], j["platform"], link, j["date"]])
    write(folder / "nadia-applied.csv",
          ["Sr", "Position Applied", "Client Name", "Job Portal", "Post Link", "Apply Date"],
          rows)

    print(f"\nWritten to {folder.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="../dummy_sheets")
    main(parser.parse_args().out)
