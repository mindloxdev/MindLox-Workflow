import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, deletedLabel } from "../api.js";
import { Loading } from "./widgets.jsx";
import { useToast } from "./shell.jsx";

const PLATFORM_OPTIONS = [
  "Indeed",
  "ZipRecruiter",
  "LinkedIn",
  "Monster",
  "Jobright.ai",
  "Glassdoor",
  "Hiring Cafe",
  "Dice",
  "Direct website",
  "AAPC Job Board",
  "SimplyHired",
  "CareerBuilder",
  "Other",
];

const COLUMNS = [
  { key: "url", label: "Job link", width: "26%", hint: "https://…" },
  { key: "title", label: "Job title", width: "20%", hint: "" },
  { key: "company", label: "Company", width: "14%", hint: "" },
  // Where the posting is written out, when that is not the apply link. The
  // apply link is usually dead three weeks later — an expired posting
  // redirects to a board's home page and takes the wording with it — and this
  // is what a BD still has when the client finally replies.
  { key: "description_url", label: "Description link", width: "20%", hint: "optional" },
  { key: "platform", label: "Platform", width: "10%", hint: "" },
  { key: "date", label: "Applied on", width: "10%", hint: "" },
  { key: "headline", label: "Headline", width: "15%", hint: "" },
];

// The team works to Eastern time. Match app/models.py if that ever changes.
const WORKING_TIMEZONE = "America/New_York";

/** Right now, where the team actually works — "2026-08-17 14:32". */
export function stampNow() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: WORKING_TIMEZONE,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date());
  const at = (type) => parts.find((p) => p.type === type)?.value || "";
  return `${at("year")}-${at("month")}-${at("day")} ${at("hour")}:${at("minute")}`;
}

// What makes a row a job: a link, or a title, or a client. The timestamp does
// not count — it is stamped for you, so every untouched row carries one and
// counting it would file blank rows as work. The platform alone identifies
// nothing either. Matches ingest.is_usable on the server.
const IDENTIFYING = ["url", "title", "company"];
const blankRow = (headline = "") => ({ url: "", title: "", company: "", description_url: "",
                          platform: "", date: stampNow(), headline });
const isEmpty = (row) => IDENTIFYING.every((key) => !String(row[key] || "").trim());

/** Rows typed in by hand, saved as this profile's sheet for the cycle.
 *
 * NOTHING SAVES UNTIL YOU SAY SO. Every cell used to write to the server on
 * blur, which meant a half-typed row — a link pasted before the title was in —
 * was already the sheet, and a row abandoned mid-thought stayed. Now a row is
 * committed when you press **+ New entry** to start the next one, or **Save
 * now**, and until then what is on screen is a draft the server has not seen.
 *
 * THE LINK IS CHECKED AS IT IS TYPED. The job link is the first thing pasted
 * and the field that identifies a posting, so it is the first moment anybody
 * can be told they are about to log something twice. The check runs against
 * the whole history, not this sheet, because the duplicate that matters is the
 * one from three weeks ago that nobody remembers.
 */
export default function EntryTable({ batchId, profileId, profileName, profileHeadline = "", onSaved }) {
  const [rows, setRows] = useState([]);
  const [state, setState] = useState("loading");   // loading | idle | dirty | saving | saved | error
  const [error, setError] = useState("");
  // The row whose link has just come back as already applied for, and what was
  // found. Null when there is nothing to say.
  const [warning, setWarning] = useState(null);    // { index, info }
  // Links the BD has been warned about and kept anyway. Keyed by the link
  // itself rather than the row number, so inserting a row above does not
  // resurrect a warning that was already answered.
  const [ignored, setIgnored] = useState(() => new Set());
  const [checking, setChecking] = useState(false);
  const lastCell = useRef(null);
  const lastSaved = useRef(null);
  const checked = useRef(new Map());               // link -> result, one ask per link
  const toast = useToast();

  /** Re-read the sheet from the server and take it as the truth.
   *
   * Used on arrival, and again after a delete. A delete is the one action
   * whose effect on the sheet is decided on the server — it strips *every* row
   * naming that posting, and a sheet can easily hold the same job twice —
   * so guessing at the result here and saving the guess would put the
   * duplicate straight back.
   */
  const reload = useCallback(async () => {
    const data = await api.listEntries(batchId, profileId);
    setRows(data.rows.length
      ? data.rows.map((row) => ({ ...row, headline: row.headline || profileHeadline }))
      : [blankRow(profileHeadline)]);
    lastSaved.current = JSON.stringify(data.rows);
    setState("idle");
    return data;
  }, [batchId, profileId, profileHeadline]);

  useEffect(() => {
    let live = true;
    setState("loading");
    api.listEntries(batchId, profileId)
      .then((data) => {
        if (!live) return;
        setRows(data.rows.length
          ? data.rows.map((row) => ({ ...row, headline: row.headline || profileHeadline }))
          : [blankRow(profileHeadline)]);
        lastSaved.current = JSON.stringify(data.rows);
        setState("idle");
      })
      .catch((err) => { if (live) { setError(err.message); setState("error"); } });
    return () => { live = false; };
  }, [batchId, profileId]);

  const save = useCallback(async (next) => {
    const payload = next.filter((r) => !isEmpty(r));
    const signature = JSON.stringify(payload);
    if (signature === lastSaved.current) {
      setState("saved");
      return true;
    }
    setState("saving");
    setError("");
    try {
      const result = await api.saveEntries(batchId, profileId, payload);
      lastSaved.current = signature;
      setState("saved");
      if (result.corrected > 0) {
        toast(result.corrected === 1
          ? "One posting was corrected for everyone holding it."
          : result.corrected + " postings were corrected for everyone holding them.");
      }
      onSaved?.(result);
      return true;
    } catch (err) {
      setError(err.message);
      setState("error");
      return false;
    }
  }, [batchId, profileId, onSaved, toast]);

  const edit = (index, key, value) => {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, [key]: value } : row)));
    setState("dirty");
  };

  /** Ask the server whether this posting has been applied for already.
   *
   * One ask per distinct link, remembered for the life of the screen — a blur
   * fires every time focus moves, and re-asking the same question of the same
   * link would be a request per keystroke in all but name.
   */
  const checkLink = useCallback(async (index, row) => {
    const url = String(row.url || "").trim();
    if (!url || ignored.has(url)) return;

    let info = checked.current.get(url);
    if (info === undefined) {
      setChecking(true);
      try {
        info = await api.checkDuplicate({
          url, title: row.title || "", company: row.company || "", profileId,
        });
        checked.current.set(url, info);
      } catch {
        return;                                    // never block typing on this
      } finally {
        setChecking(false);
      }
    }
    // Three reasons to stop somebody, in one dialog rather than three. The
    // third is advisory — a manager has flagged the client as already being
    // worked — and like the other two it never blocks the row.
    if (info?.mine || info?.others?.length || info?.being_worked) {
      setWarning({ index, info, url });
    }
  }, [ignored, profileId]);

  const addRow = async () => {
    // Pressing this is the commit. Everything typed so far goes to the server
    // before the blank row appears, so "+ New entry" means the last one is
    // filed rather than merely off the screen.
    const ok = await save(rows);
    if (!ok) return;
    setRows((current) => {
      lastCell.current = current.length;
      return [...current, blankRow(profileHeadline)];
    });
  };

  /** Take a row off the sheet — and out of the database, if it reached it.
   *
   * A row that has been through a build is not only a line on this sheet any
   * more: it is a job, an application, and possibly a dispatched row on
   * somebody's list. Removing it here and nowhere else left all three behind,
   * and the next automatic rebuild read the sheet again and put the
   * application straight back. So a row that is in the record is withdrawn
   * from the record, and one that never got there is simply dropped.
   */
  const removeRow = async (index) => {
    const row = rows[index];
    const label = row?.title || row?.company || "this row";

    if (row?.job_id && row?.in_record) {
      const ok = window.confirm(
        "Delete " + label + " from " + profileName + "'s record?\n\n"
        + "This removes the row, the application behind it and the job itself "
        + "unless a colleague also applied to it — in which case they keep "
        + "theirs. It will not come back on the next rebuild.");
      if (!ok) return;
      try {
        const result = await api.deleteEntry(row.job_id, profileId);
        setWarning(null);
        // Forget any earlier answer about this link. The posting may be gone
        // now, and re-adding it should not be met with a stale duplicate
        // warning about the entry that was just deleted.
        checked.current.delete(String(row.url || "").trim());
        // Hand the tab its new counts from what the server just returned.
        // Passing an empty object here blanked them, so the "Own jobs" tab
        // read 0 until the screen was reloaded.
        const fresh = await reload();
        onSaved?.({ row_count: fresh.row_count, usable_count: fresh.usable_count,
                    filename: fresh.filename });
        toast(deletedLabel(result, label));
      } catch (err) {
        toast(err.message, "bad");
      }
      return;
    }

    const next = rows.filter((_, i) => i !== index);
    const safe = next.length ? next : [blankRow(profileHeadline)];
    setRows(safe);
    setWarning((w) => (w && w.index === index ? null : w));
    save(safe);
  };

  // Focus the first cell of a freshly added row so you can just start typing.
  useEffect(() => {
    if (lastCell.current === null) return;
    document.getElementById(`cell-${lastCell.current}-url`)?.focus();
    lastCell.current = null;
  }, [rows.length]);

  // A draft is only on screen, so leaving the page loses it. The browser's own
  // dialog is the only thing that can interrupt a navigation in time.
  useEffect(() => {
    if (state !== "dirty") return undefined;
    const warn = (event) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [state]);

  /** Pasting a block copied out of Excel fills across columns and down rows. */
  const onPaste = (index, key, event) => {
    const text = event.clipboardData.getData("text/plain");
    if (!text || (!text.includes("\t") && !text.trim().includes("\n"))) return;
    event.preventDefault();

    const startColumn = COLUMNS.findIndex((c) => c.key === key);
    const grid = text.replace(/\r/g, "").split("\n").filter((line) => line.trim()).map((line) => line.split("\t"));

    setRows((current) => {
      const next = [...current];
      grid.forEach((cells, r) => {
        const target = index + r;
        if (!next[target]) next[target] = blankRow(profileHeadline);
        else next[target] = { ...next[target] };
        cells.forEach((value, c) => {
          const column = COLUMNS[startColumn + c];
          if (column) next[target][column.key] = value.trim();
        });
        // A pasted block usually carries no date, or an empty trailing cell.
        if (!next[target].date) next[target].date = stampNow();
      });
      // A paste is a deliberate act with everything already in it, so it is
      // committed the way a finished row is.
      save(next);
      return next;
    });
  };

  const filled = rows.filter((r) => !isEmpty(r)).length;
  const noLink = rows.filter((r) => !isEmpty(r) && !String(r.url || "").trim()).length;

  if (state === "loading") return <Loading lines={3} />;

  return (
    <div className="stack" style={{ gap: 10 }}>
      {warning && (
        <DuplicateDialog
          {...warning}
          profileName={profileName}
          onIgnore={() => {
            setIgnored((current) => new Set(current).add(warning.url));
            setWarning(null);
          }}
          onRemove={() => removeRow(warning.index)}
        />
      )}

      <div className="card scroll">
        <table>
          <thead>
            <tr>
              <th style={{ width: 34 }}>#</th>
              {COLUMNS.map((c) => <th key={c.key} style={{ width: c.width }}>{c.label}</th>)}
              <th style={{ width: 34 }} aria-label="Remove" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                <td className="mono muted" style={{ textAlign: "right" }}>{index + 1}</td>
                {COLUMNS.map((c) => {
                  const isPlatform = c.key === "platform";
                  const platformValue = isPlatform
                    ? (PLATFORM_OPTIONS.includes(row.platform) ? row.platform : (row.platform ? "Other" : ""))
                    : row[c.key] || "";
                  return (
                    <td key={c.key} style={{ padding: 3 }}>
                      {isPlatform ? (
                        <select
                          id={`cell-${index}-${c.key}`}
                          value={platformValue}
                          style={{ width: "100%", border: "1px solid transparent", background: "none" }}
                          onChange={(e) => edit(index, c.key, e.target.value)}
                        >
                          <option value="">— select —</option>
                          {PLATFORM_OPTIONS.map((option) => (
                            <option key={option} value={option}>{option}</option>
                          ))}
                          {isPlatform && row.platform && !PLATFORM_OPTIONS.includes(row.platform) && (
                            <option value={row.platform}>{row.platform}</option>
                          )}
                        </select>
                      ) : c.key === "headline" ? (
                        <span className="muted" style={{ display: "block", padding: "6px 4px" }}>
                          {row.headline || "—"}
                        </span>
                      ) : (
                        <input
                          id={`cell-${index}-${c.key}`}
                          value={row[c.key] || ""}
                          placeholder={c.hint}
                          title={c.key === "date" ? "Stamped automatically. Edit if you are backfilling." : undefined}
                          style={{ width: "100%", border: "1px solid transparent", background: "none",
                                   fontFamily: c.key === "date" ? "var(--mono)" : undefined,
                                   fontSize: c.key === "date" ? 12 : undefined,
                                   color: c.key === "date" ? "var(--slate)" : undefined }}
                          onChange={(e) => edit(index, c.key, e.target.value)}
                          onPaste={(e) => onPaste(index, c.key, e)}
                          // The link is the only field checked as it is typed:
                          // it is what identifies a posting, and the answer is
                          // worth having before the rest of the row is filled in.
                          onBlur={c.key === "url" ? () => checkLink(index, row) : undefined}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && index === rows.length - 1) addRow();
                          }}
                        />
                      )}
                    </td>
                  );
                })}
                <td style={{ textAlign: "center", padding: 3, whiteSpace: "nowrap" }}>
                  <button className="link"
                          title={row.in_record
                            ? "Delete this job — the row, the application and the "
                              + "posting itself unless a colleague also applied."
                            : "Remove this row. It has not been filed anywhere yet."}
                          onClick={() => removeRow(index)}>
                    {row.in_record ? "delete" : "\u00D7"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="row" style={{ gap: 10 }}>
          <button onClick={addRow} disabled={state === "saving"}>+ New entry</button>
          {state === "dirty" && (
            <button className="ghost" onClick={() => save(rows)}>Save now</button>
          )}
          <span className="muted">
            {filled} {filled === 1 ? "job" : "jobs"} recorded for {profileName}
          </span>
        </div>
        <span className="muted">
          {checking && "Checking the link…"}
          {!checking && state === "dirty" &&
            <span style={{ color: "var(--amber, var(--slate))" }}>Not saved yet</span>}
          {!checking && state === "saving" && "Saving…"}
          {!checking && state === "saved" && "Saved"}
          {!checking && state === "error" && <span style={{ color: "var(--brick)" }}>{error}</span>}
        </span>
      </div>

      {noLink > 0 && (
        <div className="notice">
          {noLink} {noLink === 1 ? "row has" : "rows have"} no job link. Those can only be
          matched on client plus title, so the same posting found by someone else may not be
          recognised — and they cannot be checked against what you have already applied for.
          Paste the link where you can.
        </div>
      )}

      {rows.some((r) => r.in_record) && (
        <p className="hint" style={{ marginTop: 3 }}>
          Rows marked <b>delete</b> have been through a build, so they are a job
          in the record as well as a line here. Correcting the title, client,
          platform or description link on one of those corrects the posting for
          everyone holding it. Changing the <b>job link</b> does not — that names
          a different posting, and the row becomes that job on the next build.
        </p>
      )}

      <p className="hint" style={{ marginTop: 3 }}>
        Nothing is filed until you press <b>+ New entry</b> or <b>Save now</b>.
        <b> Enter</b> on the last row does the same and starts another. Paste a
        block straight from Excel and it fills across and saves.
      </p>
    </div>
  );
}

/** What came back when a link turned out to be one already on record.
 *
 * A dialog over the page rather than a line above the table. A banner in a
 * scrolling grid is missed exactly when it matters — the BD has already moved
 * to the next cell — and this has to be answered before the row is worth
 * filling in. It takes the keyboard with it: Enter keeps the row, Escape
 * closes, and focus lands on the button that does nothing destructive.
 *
 * Two different findings, and conflating them would be wrong in opposite
 * directions. `mine` is this profile having already applied — a real duplicate,
 * one identity approaching one client twice, which is the thing this whole
 * product exists to prevent. `others` is a colleague's profile having applied,
 * which is not a duplicate at all: two candidates in the running is the reason
 * for running more than one profile. So the first is stated as a mistake and
 * the second as information.
 */
function DuplicateDialog({ info, profileName, onIgnore, onRemove }) {
  const mine = info?.mine;
  const others = info?.others || [];
  const worked = info?.being_worked;
  // What the dialog is mostly about. A duplicate outranks a colleague's
  // application, which outranks a flag — but the flag is shown either way,
  // because it is the one a BD has no other way of finding out.
  const headline = mine ? "Duplicate entry found"
    : others.length ? "Already on record"
      : "Somebody is already working this client";
  const keep = useRef(null);

  useEffect(() => { keep.current?.focus(); }, []);

  const onKeyDown = (event) => {
    if (event.key === "Escape") { event.preventDefault(); onIgnore(); }
    if (event.key === "Enter") { event.preventDefault(); onIgnore(); }
  };

  return (
    <div className="scrim" onKeyDown={onKeyDown}
         onMouseDown={(e) => e.target === e.currentTarget && onIgnore()}>
      <div className="palette" role="alertdialog" aria-modal="true"
           aria-label={headline}
           style={{ padding: "var(--s5)", gap: 12, maxHeight: "none" }}>
        <div className="stack" style={{ gap: 10 }}>
          <div className="row" style={{ gap: 8, alignItems: "baseline" }}>
            <span aria-hidden="true" style={{ fontSize: 18 }}>{mine ? "\u26A0" : "\u2139"}</span>
            <b style={{ fontFamily: "var(--display)", fontSize: "var(--t-lg)" }}>
              {headline}
            </b>
          </div>

          {mine ? (
            <p style={{ margin: 0 }}>
              <b>{profileName}</b> already applied to this posting
              {mine.applied_on ? <> on <b>{mine.applied_on}</b></> : null}
              {mine.logged && !mine.applied_on ? <> — logged {mine.logged}</> : null}.
              {" "}Applying twice under one identity is the same person approaching
              the client a second time.
            </p>
          ) : others.length === 0 ? null : (
            <p style={{ margin: 0 }}>
              This posting is already on record, under
              {" "}{others.slice(0, 3).map((o, i) => (
                <span key={`${o.profile_id}-${i}`}>
                  {i > 0 ? ", " : ""}<b>{o.profile}</b>
                  {o.applied_on ? ` (${o.applied_on})` : ""}
                </span>
              ))}
              {others.length > 3 ? ` and ${others.length - 3} more` : ""}.
              {" "}That is not a duplicate — a different profile is a different
              candidate — but it is worth knowing before you spend the time.
            </p>
          )}

          {mine && others.length > 0 && (
            <p className="hint" style={{ margin: 0 }}>
              Also applied for by {others.map((o) => o.profile).join(", ")}.
            </p>
          )}

          {/* A manager's flag, and nothing more. It has not held anything back
              and it will not: the row saves exactly as it would without it. */}
          {worked && (
            <p style={{ margin: 0 }}>
              Your manager has <b>{worked.client}</b> marked as already being
              worked{worked.by ? <> by <b>{worked.by}</b></> : null}
              {worked.since ? <> \u00b7 {worked.since}</> : null}.
              {worked.note ? <> “{worked.note}”</> : null}
              {" "}Worth a word before you spend the time — nothing here stops you
              filing the row.
            </p>
          )}

          <div className="row" style={{ gap: 10, marginTop: 2 }}>
            <button ref={keep} onClick={onIgnore}>Ignore — keep this row</button>
            <button className="ghost" onClick={onRemove}>Remove the row</button>
          </div>
          <p className="hint" style={{ margin: 0 }}>
            Ignoring is remembered for this link, so you will not be asked again.
          </p>
        </div>
      </div>
    </div>
  );
}
