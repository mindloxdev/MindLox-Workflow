"""Job identity and dispatch logic. No database, no framework — pure functions
so you can unit-test every rule in isolation.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
import urllib.parse
from collections import defaultdict
from typing import Iterable, Sequence

from rapidfuzz import fuzz

# Legal suffixes and filler words stripped before comparing client names, so
# "Acme Solutions Pvt Ltd" and "ACME Solutions" collapse to the same key.
_SUFFIX = re.compile(
    r"\b(pvt|private|ltd|limited|llc|inc|incorporated|corp|corporation|co|"
    r"gmbh|bv|nv|plc|llp|group|holdings|enterprises|international)\b"
)


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = _SUFFIX.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def client_key(company: object) -> str:
    """The key two rows share when they name the same client.

    Exactly `normalize_text`, named for what it is used for. `jobs.company_key`
    is already this, computed once at build time, so grouping postings by
    client is a plain GROUP BY — but an interview and an assessment carry the
    client as free text, and those have to be keyed at read time. Both roads
    have to arrive at the same string or one client's history splits in two.

    Deliberately not fuzzy. `fuzzy_merge` below only ever collapses two rows
    when the client *and* the title are both close, and loosening that to the
    client alone would quietly fuse two companies' whole histories — which on a
    screen a manager reads before an account call is the worst thing this
    module could do.
    """
    return normalize_text(company)


# Ordered: the first pattern that hits wins. Platform-native IDs are the most
# reliable identity there is — same job, any referral link, same ID.
#
# The third element says whether the ID is only meaningful *within one site*.
# The named platforms mint globally unique IDs, so "~01abc…" is that Upwork job
# and nothing else. The last three rules are shape-matchers — "a long number in
# the path" — and that shape repeats on every job board in existence. Without
# the hostname in the key, example.com/careers/12345678 and
# different.com/openings/12345678 collapse into one job, and one of the two
# postings silently disappears from the pool.
_ID_RULES: Sequence[tuple[re.Pattern, str, bool]] = (
    (re.compile(r"(~[0-9a-z]{12,})", re.I), "upwork", False),
    (re.compile(r"/jobs/view/(\d{6,})", re.I), "linkedin", False),
    (re.compile(r"[?&]jk=([0-9a-z]{8,})", re.I), "indeed", False),
    (re.compile(r"/projects/[^/]*?[-.](\d{6,})", re.I), "freelancer", False),
    (re.compile(r"joblistingid=(\d{5,})", re.I), "glassdoor", False),
    (re.compile(r"/(?:job|jobs|gig|project)/[^/]*?[-/](\d{6,})", re.I), "board", True),
    (re.compile(r"/(\d{7,})(?:[/?#]|$)"), "numeric", True),
    (re.compile(r"\b([0-9a-f]{16,})\b", re.I), "hexid", True),
)


# Query parameters that identify the posting rather than the search that found
# it. Everything else in a query string is dropped, which is what makes one job
# pasted through two referral links the same job.
#
# Dropping the *whole* query was the bug this list exists to fix. On plenty of
# job sites the posting id lives nowhere else:
#
#   teamhealthcareers.com/...HomeWithPreLoad?partnerid=26628&jobid=854227
#   workforcenow.adp.com/...recruitment.html?ccId=19000101&jobId=56949
#   linkedin.com/jobs/search-results/?currentJobId=4460596778
#   indeed.com/jobs?q=medical+scheduler&vjk=424643485d2702f8
#
# Strip the query on those and every posting on the site collapses into one
# row: one team's live data had five different TeamHealth jobs, eight ADP jobs
# and eighteen Indeed jobs at eighteen different companies all fused into a
# single job each, which blocks dispatch and fires "you already applied" on
# work nobody has touched.
#
# Named conservatively. A parameter has to look like a *job* id to be kept: a
# bare `id` is as likely to be a session token, and keeping one of those would
# split one posting into a new row on every visit — the opposite mistake, and
# one that hands the same job out twice.
_ID_PARAMS = frozenset({
    "jobid", "jobno", "jobcode", "jobseqno", "jobopeningid", "currentjobid",
    "vjk", "jk", "gh_jid", "opportunityid", "postingid", "postingseq",
    "requisitionid", "reqid", "req", "vacancyid", "positionid",
    "career_job_req_id", "indeedapplyablejobid",
})


def canonical_url(raw: object) -> str:
    """Strip protocol, www, the fragment, tracking params and trailing slash.

    What survives is the host, the path, and any query parameter that names the
    posting — see `_ID_PARAMS`. Kept parameters are sorted, so the same job
    pasted with its arguments in a different order is still the same job.
    """
    text = str(raw or "").strip()
    if not text or "." not in text:
        return ""
    text = text.lower()
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"^www\.", "", text)
    text = text.split("#")[0]
    head, _, query = text.partition("?")
    head = head.rstrip("/")
    keep = sorted((key, value) for key, value in urllib.parse.parse_qsl(query)
                  if key in _ID_PARAMS and value)
    if keep:
        head += "?" + "&".join(f"{key}={value}" for key, value in keep)
    return head


# The tail an apply flow adds to a listing. One posting, reached two ways: a
# colleague browsing pastes the listing, a colleague who actually applied
# pastes whatever the apply button left in the address bar. Workday appends
# /apply/autofillWithResume, iCIMS appends /job, a dozen others append /apply.
#
# Only ever stripped from the END, and only these words. Cutting on depth
# instead — "the first two path segments identify the posting" — reads
# ovationhealthcare.../en-US/ovationhealthcare as the identity and collapses
# every job at that employer into one.
# Two kinds, and the difference matters. The first may carry a sub-path of its
# own — Workday's /apply/autofillWithResume — so it swallows whatever follows.
# The second must be the very last segment: "job" and "jobs" sit in the middle
# of nearly every careers URL there is, and letting those swallow the rest
# turns careers.acme.com/jobs/48213/ar-specialist into careers.acme.com, which
# is every job at Acme.
_APPLY_TAIL = re.compile(
    r"/(apply|apply-now|applynow|application|applications|submit|"
    r"submit-application|autofillwithresume)(?:/.*)?$", re.I)
_APPLY_LAST = re.compile(
    r"/(job|jobs|start|begin|login|signin|register|confirm|review)$", re.I)


def posting_stem(raw: object) -> str:
    """One posting, however it was linked.

    The listing and its own apply flow are the same job to a person and two
    different URLs to a fingerprint, so a posting somebody has already applied
    for or turned down comes back as a fresh row with no history against it.
    This is what makes them equal again.

    Deliberately narrow. It merges a URL with its own apply flow and nothing
    else: two genuinely different openings have different stems, because the
    part that identifies them is still in there.
    """
    clean = canonical_url(raw)
    if not clean or "/" not in clean:
        return ""
    if "?" in clean:
        return clean
    previous = None
    while previous != clean:
        previous = clean
        clean = _APPLY_LAST.sub("", _APPLY_TAIL.sub("", clean))
        if "/" not in clean:
            return ""
    return clean


def split_url(raw: object) -> tuple[str, str]:
    """(host, path) from a canonical URL. Both empty when there is no usable host."""
    clean = canonical_url(raw).split("?")[0]
    if not clean:
        return "", ""
    site, _, rest = clean.partition("/")
    return site, "/" + rest


# `jobs.fingerprint` is VARCHAR(400). Nothing upstream bounds what goes into
# one — a Workday path can spell the whole job title out, and an L3 key is a
# client name and a title glued together — so a single very long posting used
# to fail the whole build's INSERT with "value too long for type character
# varying(400)" and take every other job in the cycle down with it.
_FINGERPRINT_MAX = 400
_FINGERPRINT_DIGEST = 16


def _bounded(mark: str) -> str:
    """Cap a fingerprint at the width of the column that has to hold it.

    Plain truncation would fuse two postings that share a long prefix — the
    same careers site, the same department, different job — which is exactly
    the silent merge this module exists to prevent. Replacing the tail with a
    digest of the whole thing keeps the key inside the column and still tells
    those two apart, and it is derived only from the input, so the same posting
    fingerprints identically on every run and in every caller.
    """
    if len(mark) <= _FINGERPRINT_MAX:
        return mark
    digest = hashlib.sha1(mark.encode("utf-8")).hexdigest()[:_FINGERPRINT_DIGEST]
    return mark[:_FINGERPRINT_MAX - _FINGERPRINT_DIGEST - 1] + "~" + digest


def fingerprint(url: object, title: object, company: object) -> tuple[str, str]:
    """Return (fingerprint, tier). Empty fingerprint means the row is unusable."""
    raw_url = str(url or "").strip()
    if raw_url:
        site, path = split_url(raw_url)
        for pattern, tag, site_scoped in _ID_RULES:
            if site_scoped and not site:
                continue
            # Site-scoped rules read the path only. A 16-hex run in a query
            # string is a tracking token shared across a whole session, not a
            # job ID, and matching on it fuses unrelated postings.
            hit = pattern.search(path if site_scoped else raw_url)
            if hit:
                value = hit.group(1).lower()
                return _bounded(f"id:{tag}:{site}:{value}" if site_scoped
                                else f"id:{tag}:{value}"), "L1"
        clean = canonical_url(raw_url)
        if len(clean) > 8:
            return _bounded(f"url:{clean}"), "L2"

    client = normalize_text(company)
    role = normalize_text(title)
    if not client and not role:
        return "", "-"
    return _bounded(f"ct:{client}|{role}"), "L3"


def bucket_key(company: object) -> str:
    """Leading word of the client name.

    Bucketing on the *whole* name is too strict — "Northwind" and "Northwind
    Digital" would never meet. Bucketing on the first word brings them together
    cheaply; the similarity checks below decide whether they are really the same.
    """
    clean = normalize_text(company)
    return clean.split(" ")[0] if clean else ""


def fuzzy_merge(records: Iterable[dict], threshold: int = 88,
                client_threshold: int = 82) -> dict[str, str]:
    """Collapse near-identical L3 fingerprints.

    Two rows merge only if the client names are close *and* the titles are
    close. Requiring both keeps "React Developer at Northwind" apart from
    "React Developer at Bluepeak", which a title-only test would happily fuse.
    """
    buckets: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        if record.get("tier") != "L3":
            continue
        buckets[bucket_key(record.get("company"))].append(record)

    remap: dict[str, str] = {}
    for group in buckets.values():
        if len(group) < 2:
            continue
        reps: list[tuple[str, str, str]] = []  # (fingerprint, client, title)
        for record in group:
            client = normalize_text(record.get("company"))
            role = normalize_text(record.get("title"))
            match = None
            for rep_fp, rep_client, rep_role in reps:
                if (fuzz.token_set_ratio(client, rep_client) >= client_threshold
                        and fuzz.token_set_ratio(role, rep_role) >= threshold):
                    match = rep_fp
                    break
            if match is None:
                reps.append((record["fp"], client, role))
            elif match != record["fp"]:
                remap[record["fp"]] = match
    return remap


# --------------------------------------------------------------------------- #
# Who else should be in this cycle
# --------------------------------------------------------------------------- #

# Words that say what somebody is rather than what they can do. Stripped
# before two skills are compared, for the same reason _SUFFIX strips "Ltd"
# from a client name: they are on nearly every entry, so leaving them in means
# "React Engineer" and "AI Engineer" score 84 on the word "engineer" alone and
# a front-end profile gets pulled into an AI cycle.
_ROLE_NOISE = re.compile(
    r"\b(engineer|engineering|developer|dev|programmer|specialist|consultant|"
    r"expert|professional|senior|junior|lead|principal|staff|sr|jr|mid|level|"
    r"years|experience|freelance|freelancer|contractor|remote)\b"
)


def skill_set(value: object) -> set[str]:
    """One profile's skills as comparable tokens.

    Split on commas, slashes, pipes and semicolons, because a skills field is
    typed by a person and "Python, PyTorch / RAG" is as common as any tidier
    form. Each entry then goes through the same normaliser client names take,
    plus the role words above.

    An entry that is nothing but role words — a skills field reading
    "Senior Developer" — comes out empty and is dropped rather than kept as a
    token everybody would match on.
    """
    parts = re.split(r"[,/|;]+", str(value or ""))
    out = set()
    for part in parts:
        token = _ROLE_NOISE.sub(" ", normalize_text(part))
        token = re.sub(r"\s+", " ", token).strip()
        # A bare number is what "5 years experience" leaves behind once the
        # role words are gone, and two profiles both claiming five years would
        # otherwise match on the digit alone.
        if token and not token.isdigit():
            out.add(token)
    return out


# Skills so widely shared that having one in common says nothing about whether
# two profiles sell the same thing. Infrastructure and tooling, not languages:
# an AI engineer and a front-end engineer both run Postgres in Docker on AWS,
# and matching on that is how a full-stack profile ends up in an AI cycle.
#
# Deliberately excludes languages and frameworks. Two profiles both listing
# Python, or both listing React, really are in the same market — that is the
# Khuram-and-Zahid case this whole feature exists for.
_COMMON_SKILLS = {
    "git", "github", "gitlab", "docker", "kubernetes", "k8s", "aws", "azure",
    "gcp", "google cloud", "cloud", "linux", "unix", "bash", "shell",
    "sql", "postgres", "postgresql", "mysql", "sqlite", "mongodb", "mongo",
    "redis", "nginx", "rest", "rest api", "api", "apis", "json", "xml",
    "html", "css", "agile", "scrum", "jira", "ci", "cd", "ci cd", "devops",
    "testing", "unit testing", "debugging", "communication", "english",
}


def _meaningful(skills: set[str]) -> set[str]:
    """The skills that can carry a match on their own."""
    return {skill for skill in skills
            if skill not in _COMMON_SKILLS and skill.replace(" ", "") not in _COMMON_SKILLS}


def _squashed(skills: set[str]) -> set[str]:
    """The same skills with the spaces taken out.

    normalize_text turns punctuation into spaces, so "Node.js" becomes the two
    tokens "node js" while somebody else's "nodejs" stays one. Compared as
    written those score 62 and never meet; squashed, they are the same string.
    Cheaper and more exact than dropping the fuzzy threshold far enough to
    catch them, which would start fusing genuinely different skills.
    """
    return {skill.replace(" ", "") for skill in skills}


def skills_overlap(a: object, b: object, threshold: int = 82) -> bool:
    """Whether two profiles are selling near enough the same thing.

    Used to decide which profiles join a cycle they have not handed a sheet
    into. Shared tooling is dropped first — see _COMMON_SKILLS — and then three
    passes, cheapest first: the skills as written, the skills with punctuation
    squashed out ("Node.js" against "nodejs"), then fuzzy, which is what catches
    "LLM" against "LLMs" and "Postgres" against "PostgreSQL".

    One shared skill is enough on purpose. Requiring a proportion of them to
    match would punish a profile for listing its skills in detail, and the cost
    of a loose match here is one extra job on a list somebody skips in a second
    — against the cost of a tight one, which is the profile with spare capacity
    being the only profile handed nothing.

    88 was too tight to be useful on real skills fields and 82 is where "Java"
    against "JavaScript" (57) and "React" against "Redux" (40) are still
    comfortably apart. Raise it if you see unrelated profiles being pulled into
    each other's cycles.
    """
    left, right = _meaningful(skill_set(a)), _meaningful(skill_set(b))
    if not left or not right:
        return False
    if left & right or _squashed(left) & _squashed(right):
        return True
    return any(fuzz.token_set_ratio(one, two) >= threshold
               for one in left for two in right)


def similar_profiles(participants: Sequence[dict], others: Sequence[dict],
                     threshold: int = 82) -> list[int]:
    """Profiles that should receive this cycle's pool without having fed it.

    A cycle opens, two BDs hand in their sheets, and a third profile selling
    the same skills has logged nothing yet — because they are new, or were away,
    or simply have not got to it. Leaving them out means the one person with
    spare capacity is the one person given no work, which is exactly backwards.

    Matched on skills rather than on the headline, so "AI Engineer" and "ML
    Engineer" are recognised as the same market. A profile with no skills
    recorded is never pulled in: an empty field is not a match, it is a profile
    nobody has finished setting up, and handing it a stranger's pool would be a
    guess rather than an inference.

    Entries are {"id": int, "skills": str} on both sides.
    """
    out = []
    for candidate in others:
        if any(skills_overlap(candidate.get("skills"), member.get("skills"), threshold)
               for member in participants):
            out.append(candidate["id"])
    return sorted(out)


def cover(
    pool: Sequence[dict],
    holder_ids: Sequence[int],
    quota: int,
    one_per_client: bool = False,
) -> tuple[dict[int, list[int]], dict]:
    """Give every profile every job it has not already worked.

    pool entries: {"job_id": int, "company_key": str, "blocked_for": set[int]}
    A pool entry may also include `headlines`, limiting it to profiles with
    one of the same headlines as the profiles that applied, and `defer`, which
    holds it back until everything not deferred has been placed.
    `blocked_for` is who must NOT receive it — the profiles that already applied
    to it, plus the ones that looked at it and skipped it.

    This is the default because two profiles are two different candidates. If
    Khuram applied to a job, that is no reason for Zahid not to: the client sees
    two applicants, not one applying twice. So the pool is not divided up — it
    is offered to everyone who has not personally used it.

    Ali's profile logged 30 jobs and Sara's logged 50, sharing none: the pool is
    80, Ali's profile gets back the 50 it has not seen, Sara's gets back the 30.

    Jobs almost nobody can take are placed first. With a tight quota that is
    what decides whether a rare opening reaches anyone at all: spend the last
    slot on a job three profiles could have taken and the one only a single
    profile was eligible for reaches nobody.
    """
    assigned: dict[int, list[int]] = {holder: [] for holder in holder_ids}
    clients_seen: dict[int, set[str]] = {holder: set() for holder in holder_ids}
    saturated = 0
    by_client = 0
    by_quota = 0
    placements = 0

    candidates = []
    for job in pool:
        headlines = job.get("headlines")
        takers = [h for h in holder_ids
              if h not in job["blocked_for"]
              and (not headlines or job.get("headline_by_profile", {}).get(h) in headlines)]
        if not takers:
            saturated += 1
            continue
        candidates.append((job.get("defer", 0), len(takers), job, takers))

    # Deferred jobs last, then scarcest first within each group. `defer` is how
    # a caller says "this one is real, and worth having, but it is not what this
    # cycle is about" — today it marks a posting back-loaded out of somebody's
    # old spreadsheets. Three months of those would otherwise spend the whole
    # cap before a BD's list reached anything found this week, and the two are
    # not worth the same: a posting from June may well be filled.
    candidates.sort(key=lambda item: (item[0], item[1]))

    for _, _, job, takers in candidates:
        client = job.get("company_key") or ""
        placed = 0
        blocked_by_client = False
        for holder in takers:
            if len(assigned[holder]) >= quota:
                continue
            if one_per_client and client and client in clients_seen[holder]:
                blocked_by_client = True
                continue
            assigned[holder].append(job["job_id"])
            if client:
                clients_seen[holder].add(client)
            placed += 1

        placements += placed
        if placed == 0:
            if blocked_by_client:
                by_client += 1
            else:
                by_quota += 1

    return assigned, {
        "saturated": saturated,
        "held_back": by_client + by_quota,
        "held_back_client": by_client,
        "held_back_quota": by_quota,
        "rebalanced": 0,
        "placements": placements,
    }


def partition(
    pool: Sequence[dict],
    holder_ids: Sequence[int],
    quota: int,
    one_per_client: bool = True,
) -> tuple[dict[int, list[int]], dict]:
    """Hand every job to exactly one profile that has not already worked it.

    pool entries: {"job_id": int, "company_key": str, "blocked_for": set[int]}

    The alternative to `cover`, for a team where one job going to two people
    would mean the same identity applying twice. Two rules make the split fair
    rather than merely disjoint:

      1. Jobs with the fewest eligible holders are placed first. A job only one
         profile can take must be given to it before its quota fills up with
         jobs anyone could have taken. `defer` outranks it: a back-loaded
         posting waits for everything this cycle gathered, however scarce.
      2. Among eligible holders, the one holding the fewest jobs so far wins.
         Without this you get one sheet with 300 rows and another with four.
    """
    assigned: dict[int, list[int]] = {holder: [] for holder in holder_ids}
    clients_seen: dict[int, set[str]] = {holder: set() for holder in holder_ids}
    saturated = 0
    by_client = 0
    by_quota = 0

    candidates = []
    for job in pool:
        headlines = job.get("headlines")
        eligible = [uid for uid in holder_ids
                if uid not in job["blocked_for"]
                and (not headlines or job.get("headline_by_profile", {}).get(uid) in headlines)]
        if not eligible:
            saturated += 1
            continue
        candidates.append((job.get("defer", 0), len(eligible), job, eligible))

    # Deferred last, scarcest first inside each group — see cover().
    candidates.sort(key=lambda item: (item[0], item[1]))

    for _, _, job, eligible in candidates:
        client = job.get("company_key") or ""
        ranked = sorted(eligible, key=lambda uid: (len(assigned[uid]), uid))
        chosen = None
        blocked_by_client = False
        for uid in ranked:
            if len(assigned[uid]) >= quota:
                continue
            if one_per_client and client and client in clients_seen[uid]:
                blocked_by_client = True
                continue
            chosen = uid
            break
        if chosen is None:
            # Which constraint actually bound matters to the manager: a full
            # quota means "we ran out of room", the client rule means "we ran
            # out of *distinct clients*", and those call for opposite fixes.
            if blocked_by_client:
                by_client += 1
            else:
                by_quota += 1
            continue
        assigned[chosen].append(job["job_id"])
        if client:
            clients_seen[chosen].add(client)

    lookup = {job["job_id"]: job for job in pool}
    moves = _rebalance(assigned, lookup, one_per_client)

    return assigned, {
        "saturated": saturated,
        "held_back": by_client + by_quota,
        "held_back_client": by_client,
        "held_back_quota": by_quota,
        "rebalanced": moves,
        "placements": sum(len(jobs) for jobs in assigned.values()),
    }


def _rebalance(assigned: dict[int, list[int]], lookup: dict[int, dict],
               one_per_client: bool, max_rounds: int = 2000) -> int:
    """Even out the sheets after the greedy pass.

    Greedy always places a job with the person holding fewest jobs *at that
    moment*, which is not the same as fewest at the end. This walks the result
    and hands work from the busiest person to the quietest one whenever that is
    legal, until the gap is down to one job or nothing more can move.

    Each person's client tally is carried between rounds rather than rebuilt
    from their whole sheet on every comparison — that inner rebuild made the
    pass cost O(rounds x people x jobs), which is what made it crawl on a real
    team's worth of data.
    """
    clients: dict[int, dict[str, int]] = {}
    for uid, job_ids in assigned.items():
        tally: dict[str, int] = defaultdict(int)
        if one_per_client:
            for job_id in job_ids:
                key = lookup[job_id].get("company_key") or ""
                if key:
                    tally[key] += 1
        clients[uid] = tally

    moves = 0
    for _ in range(max_rounds):
        order = sorted(assigned, key=lambda uid: len(assigned[uid]))
        moved = False
        for heavy in reversed(order):
            for light in order:
                # order runs lightest-first, so once the gap closes against the
                # lightest person it has closed against everyone.
                if len(assigned[heavy]) - len(assigned[light]) <= 1:
                    break
                for job_id in assigned[heavy]:
                    job = lookup[job_id]
                    if light in job["blocked_for"]:
                        continue
                    headlines = job.get("headlines")
                    if headlines and job.get("headline_by_profile", {}).get(light) not in headlines:
                        continue
                    key = job.get("company_key") or ""
                    if one_per_client and key and clients[light].get(key):
                        continue
                    assigned[heavy].remove(job_id)
                    assigned[light].append(job_id)
                    if one_per_client and key:
                        clients[light][key] += 1
                        clients[heavy][key] -= 1
                        if clients[heavy][key] <= 0:
                            del clients[heavy][key]
                    moves += 1
                    moved = True
                    break
                if moved:
                    break
            if moved:
                break
        if not moved:
            break
    return moves


def overlap_matrix(pool: Sequence[dict], holder_ids: Sequence[int]) -> dict[int, dict[int, int]]:
    """matrix[a][b] = jobs both a and b applied to. Diagonal = that profile's total.

    Unlike the dispatch functions this one really does mean *applied*, not
    applied-or-skipped: it is a report on effort already spent.
    """
    matrix = {a: {b: 0 for b in holder_ids} for a in holder_ids}
    for job in pool:
        applicants = [uid for uid in job["applied_by"] if uid in matrix]
        for a in applicants:
            for b in applicants:
                matrix[a][b] += 1
    return matrix
