"""Run with:  pytest test_matching.py -v

These cover the rules that actually matter. If you change the fingerprint tiers
or the partition strategy, these tell you immediately whether you broke the
guarantee that no two people get the same job.
"""
from app.ingest import safe_url
from app.matching import (canonical_url, cover, fingerprint, fuzzy_merge,
                          normalize_text, overlap_matrix, partition)


def test_same_upwork_job_different_links():
    a, _ = fingerprint("https://www.upwork.com/jobs/~01abcdef1234567890", "React dev", "Acme")
    b, _ = fingerprint("https://upwork.com/jobs/~01abcdef1234567890?utm_source=email", "React Developer", "ACME Ltd")
    assert a == b


def test_linkedin_and_indeed_ids():
    a, tier = fingerprint("https://www.linkedin.com/jobs/view/3912345678/?trk=feed", "x", "y")
    assert tier == "L1" and a.endswith("3912345678")
    b, tier = fingerprint("https://pk.indeed.com/viewjob?jk=a1b2c3d4e5f60718&from=serp", "x", "y")
    assert tier == "L1" and "a1b2c3d4e5f60718" in b


def test_url_fallback_strips_tracking():
    assert canonical_url("HTTPS://WWW.Example.com/jobs/42/?ref=x#top") == "example.com/jobs/42"


def test_client_suffixes_are_ignored():
    assert normalize_text("Orchard Retail Pvt Ltd") == normalize_text("ORCHARD RETAIL")


def test_a_bare_id_does_not_reach_across_sites():
    """"/12345678" is a shape every board uses. Two boards, two different jobs."""
    a, tier = fingerprint("https://example.com/careers/12345678", "Job A", "X")
    b, _ = fingerprint("https://different.com/openings/12345678", "Job B", "Y")
    assert tier == "L1" and a != b


def test_the_same_id_on_the_same_site_still_matches():
    a, _ = fingerprint("https://example.com/careers/12345678", "Job A", "X")
    b, _ = fingerprint("http://www.example.com/careers/12345678?src=digest", "Job A", "X")
    assert a == b


def test_a_tracking_token_is_not_mistaken_for_a_job_id():
    """A 16-hex run in the query is a session token shared by every link in a
    digest email — matching on it would fuse the whole email into one job."""
    a, _ = fingerprint("https://example.com/careers/react-dev?sid=a1b2c3d4e5f60718", "A", "X")
    b, _ = fingerprint("https://example.com/careers/python-dev?sid=a1b2c3d4e5f60718", "B", "X")
    assert a != b


def test_javascript_links_are_dropped_at_the_door():
    assert safe_url("javascript:alert(document.domain)") == ""
    assert safe_url("data:text/html,<script>x</script>") == ""
    assert safe_url("https://www.upwork.com/jobs/~01abc") == "https://www.upwork.com/jobs/~01abc"
    assert safe_url("www.upwork.com/jobs/~01abc") == "www.upwork.com/jobs/~01abc"


def test_no_link_falls_back_to_client_and_title():
    fp, tier = fingerprint("", "Senior React Developer", "Northwind Digital")
    assert tier == "L3" and fp.startswith("ct:")


def test_unusable_row_is_rejected():
    assert fingerprint("", "", "")[0] == ""


def test_fuzzy_merge_collapses_reworded_titles():
    records = [
        {"fp": "ct:northwind|senior react developer", "tier": "L3",
         "title": "Senior React Developer", "company": "Northwind"},
        {"fp": "ct:northwind|react developer senior urgent", "tier": "L3",
         "title": "React Developer Senior - Urgent", "company": "Northwind Digital"},
    ]
    remap = fuzzy_merge(records)
    assert len(remap) == 1


def test_fuzzy_merge_keeps_different_clients_apart():
    records = [
        {"fp": "a", "tier": "L3", "title": "React Developer", "company": "Northwind"},
        {"fp": "b", "tier": "L3", "title": "React Developer", "company": "Bluepeak"},
    ]
    assert fuzzy_merge(records) == {}


def test_partition_never_repeats_a_job():
    pool = [{"job_id": i, "company_key": f"c{i}", "blocked_for": set()} for i in range(30)]
    assigned, _ = partition(pool, [1, 2, 3], quota=40)
    flat = [j for jobs in assigned.values() for j in jobs]
    assert len(flat) == len(set(flat)) == 30


def test_partition_never_gives_you_your_own_job():
    pool = [{"job_id": 1, "company_key": "x", "blocked_for": {1}},
            {"job_id": 2, "company_key": "y", "blocked_for": {2}}]
    assigned, _ = partition(pool, [1, 2], quota=40)
    assert 1 not in assigned[1] and 2 not in assigned[2]


# --------------------------------------------------------------------------- #
# Coverage mode — the default. Two profiles are two candidates, so a job one of
# them has used is still worth the other's time.
# --------------------------------------------------------------------------- #

def test_cover_hands_back_exactly_what_you_have_not_tried():
    """Khuram logged jobs 0-29, Zahid logged 20-69. Pool of 70, shared 10.

    Khuram should get the 40 it has never seen, Zahid the 20 it has never seen.
    """
    khuram, zahid = 1, 2
    pool = []
    for job_id in range(70):
        blocked = set()
        if job_id < 30:
            blocked.add(khuram)
        if 20 <= job_id < 70:
            blocked.add(zahid)
        pool.append({"job_id": job_id, "company_key": f"c{job_id}", "blocked_for": blocked})

    assigned, stats = cover(pool, [khuram, zahid], quota=500, one_per_client=False)
    assert len(assigned[khuram]) == 40
    assert len(assigned[zahid]) == 20
    assert stats["saturated"] == 10        # the ten both had already used


def test_cover_gives_the_same_job_to_two_profiles():
    """The whole point: one posting, two candidates, both may apply."""
    pool = [{"job_id": 7, "company_key": "acme", "blocked_for": set()}]
    assigned, _ = cover(pool, [1, 2, 3], quota=40, one_per_client=False)
    assert assigned[1] == assigned[2] == assigned[3] == [7]


def test_cover_never_gives_a_profile_its_own_job():
    pool = [{"job_id": 1, "company_key": "x", "blocked_for": {1}},
            {"job_id": 2, "company_key": "y", "blocked_for": {2}}]
    assigned, _ = cover(pool, [1, 2], quota=40, one_per_client=False)
    assert assigned[1] == [2] and assigned[2] == [1]


def test_cover_respects_the_quota():
    pool = [{"job_id": i, "company_key": f"c{i}", "blocked_for": set()} for i in range(50)]
    assigned, stats = cover(pool, [1, 2], quota=10, one_per_client=False)
    assert len(assigned[1]) == len(assigned[2]) == 10
    assert stats["held_back_quota"] == 40 and stats["held_back_client"] == 0


def test_cover_places_the_scarcest_jobs_first():
    """A job only one profile is eligible for must not lose its slot to a job
    everybody could have taken."""
    pool = [
        {"job_id": 1, "company_key": "a", "blocked_for": {2, 3}},   # only holder 1 can take it
        {"job_id": 2, "company_key": "b", "blocked_for": set()},    # anyone can
        {"job_id": 3, "company_key": "c", "blocked_for": set()},
    ]
    assigned, _ = cover(pool, [1, 2, 3], quota=1, one_per_client=False)
    assert assigned[1] == [1], "the scarce job should have gone out first"


def test_cover_counts_jobs_nobody_can_take():
    pool = [{"job_id": 1, "company_key": "x", "blocked_for": {1, 2}}]
    assigned, stats = cover(pool, [1, 2], quota=40, one_per_client=False)
    assert stats["saturated"] == 1 and not any(assigned.values())


def test_partition_balances_the_load():
    pool = [{"job_id": i, "company_key": f"c{i}", "blocked_for": set()} for i in range(30)]
    assigned, _ = partition(pool, [1, 2, 3], quota=40)
    sizes = sorted(len(v) for v in assigned.values())
    assert sizes[-1] - sizes[0] <= 1


def test_partition_respects_the_quota():
    pool = [{"job_id": i, "company_key": f"c{i}", "blocked_for": set()} for i in range(100)]
    assigned, _ = partition(pool, [1, 2], quota=10)
    assert all(len(v) <= 10 for v in assigned.values())


def test_saturated_jobs_are_dropped():
    pool = [{"job_id": 1, "company_key": "x", "blocked_for": {1, 2}}]
    assigned, stats = partition(pool, [1, 2], quota=40)
    assert stats["saturated"] == 1 and not any(assigned.values())


def test_one_job_per_client_rule():
    pool = [{"job_id": i, "company_key": "sameclient", "blocked_for": set()} for i in range(5)]
    assigned, stats = partition(pool, [1], quota=40, one_per_client=True)
    assert len(assigned[1]) == 1 and stats["held_back"] == 4
    assert stats["held_back_client"] == 4 and stats["held_back_quota"] == 0


def test_the_quota_is_not_blamed_on_the_client_rule():
    """Told the wrong reason, a manager fixes the wrong thing."""
    pool = [{"job_id": i, "company_key": f"c{i}", "blocked_for": set()} for i in range(10)]
    assigned, stats = partition(pool, [1], quota=3, one_per_client=False)
    assert len(assigned[1]) == 3
    assert stats["held_back_quota"] == 7 and stats["held_back_client"] == 0


def test_overlap_matrix_counts_pairs():
    pool = [{"applied_by": {1, 2}}, {"applied_by": {1}}, {"applied_by": {1, 2, 3}}]
    matrix = overlap_matrix(pool, [1, 2, 3])
    assert matrix[1][1] == 3      # Ali applied to three
    assert matrix[1][2] == 2      # two of them Hina also hit
    assert matrix[2][3] == 1
