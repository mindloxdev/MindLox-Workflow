import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";

/** Back-loading the months of applying that happened before this app.
 *
 * A BD who has been working out of a spreadsheet since June arrives here with
 * three thousand rows and nothing in the system to show for them, so the app
 * hands them back postings they worked in July and nobody's figures are true.
 * This is where they put it right themselves, with their own file, as many
 * times as it takes.
 *
 * Three things about it are worth saying out loud on the screen, because each
 * one is a question somebody will otherwise ask their manager:
 *
 *   1. It is not this cycle's sheet. It goes into the profile's all-time
 *      record, not into this week's figures.
 *   2. Handing in the same file again is safe, and is the repair when rows go
 *      missing. Everything already on record is recognised and left alone.
 *   3. A run that is interrupted is not a run that has to start over.
 */

const FIELD_LABELS = {
  url: "Job link",
  title: "Job title",
  company: "Company",
  platform: "Platform",
  date: "Applied on",
  description_url: "Job description link",
};

const count = (n) => (n ?? 0).toLocaleString();

/** What one finished run actually did, in the order somebody asks it.
 *
 * "Added" first, because that is the answer to "did my work get in". "Already
 * on record" second, because on a second run of the same file it is nearly all
 * of it and reads as a failure unless it is named as the thing that makes a
 * re-import safe. "Unreadable" last and only when there are any — those rows
 * are the only ones no amount of re-importing will ever fix.
 */
function Tally({ run, rowCount }) {
  if (!run) return null;
  return (
    <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
      <span className="pill on">{count(run.added)} added</span>
      {run.already > 0 && (
        <span className="pill" title="Already in this profile's record, so left exactly as they were — not written twice, not re-dated.">
          {count(run.already)} already on record
        </span>
      )}
      {run.unusable > 0 && (
        <span className="pill warn" title="No job link, no client and no title — there is nothing here to identify a posting by, so no import can ever file these.">
          {count(run.unusable)} unreadable
        </span>
      )}
      <span className="muted" style={{ fontSize: 12 }}>
        of {count(rowCount)} rows in the file
      </span>
    </div>
  );
}

export default function ImportHistory({ profileId, profileName, onWrote }) {
  const [past, setPast] = useState([]);
  const [current, setCurrent] = useState(null);   // the sheet being set up or run
  const [run, setRun] = useState(null);           // the progress of the run
  const [share, setShare] = useState(true);
  const [busy, setBusy] = useState(false);
  const [hot, setHot] = useState(false);
  const [note, setNote] = useState(null);
  const fileInput = useRef(null);
  // Set when somebody presses stop. The loop checks it between chunks rather
  // than aborting a request in flight, so stopping never costs the rows that
  // were being written when it was pressed.
  const stop = useRef(false);

  const reload = useCallback(() => {
    if (!profileId) return;
    api.imports(profileId).then((d) => setPast(d.imports || [])).catch(() => {});
  }, [profileId]);

  useEffect(() => { reload(); }, [reload]);
  useEffect(() => { setCurrent(null); setRun(null); setNote(null); }, [profileId]);

  const read = async (file) => {
    if (!file || !profileId) return;
    setBusy(true);
    setNote(null);
    setRun(null);
    try {
      const data = await api.startImport(profileId, file, share);
      setCurrent(data);
      if (!data.batch_open) {
        setNote({ text: "No cycle is open, so these will go into "
                      + `${profileName}'s own record and reach nobody else. `
                      + "Import them during a cycle if you want colleagues offered them." });
      }
      reload();
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const remap = async (key, value) => {
    const mapping = { ...current.mapping, [key]: value };
    setCurrent({ ...current, mapping });
    try {
      const saved = await api.updateImport(current.id, { mapping });
      setCurrent((now) => (now && now.id === saved.id ? { ...now, ...saved } : now));
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  /** Walk the sheet to the end, a chunk per request.
   *
   * The loop is here rather than on the server so the screen can say how far it
   * has got on a file this long, and so closing the tab is a pause rather than
   * a failure — every chunk is committed on its own and the import remembers
   * where it stopped.
   */
  const write = async (record) => {
    stop.current = false;
    setBusy(true);
    setNote(null);
    setCurrent(record);
    try {
      let last = null;
      do {
        last = await api.runImport(record.id);
        setRun(last);
      } while (!last.done && !stop.current);

      if (last.done) {
        setNote({
          text: `${count(last.added)} added to ${profileName}'s record`
              + (last.already ? `, ${count(last.already)} were already there` : "")
              + (last.unusable ? `, ${count(last.unusable)} unreadable` : "")
              + ".",
        });
        onWrote?.();
      } else {
        setNote({ text: `Stopped at row ${count(last.cursor)} of ${count(last.row_count)}. `
                      + "Nothing written is lost — press resume to carry on." });
      }
      reload();
    } catch (err) {
      setNote({ bad: true, text: `${err.message} Everything written so far is `
                                 + "safe — press resume to carry on from there." });
      reload();
    } finally {
      setBusy(false);
    }
  };

  const setShared = async (record, value) => {
    try {
      const saved = await api.updateImport(record.id, { share_with_team: value });
      setPast((rows) => rows.map((r) => (r.id === saved.id ? { ...r, ...saved } : r)));
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  const forget = async (record) => {
    try {
      await api.deleteImport(record.id);
      if (current?.id === record.id) { setCurrent(null); setRun(null); }
      setNote({ text: "That sheet is forgotten. What it filed stays in the record — "
                    + "those are applications now." });
      reload();
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  const started = (current?.cursor || 0) > 0 || !!run;
  const done = run?.done || current?.status === "done";
  const rowCount = run?.row_count ?? current?.row_count ?? 0;
  const through = run?.cursor ?? current?.cursor ?? 0;
  const unfinished = past.filter((r) => r.status !== "done" && r.id !== current?.id);

  return (
    <section className="stack" style={{ gap: 12 }}>
      <div>
        <h3>Bring in work from before this app</h3>
        <p className="hint" style={{ marginTop: 3, maxWidth: 680 }}>
          Your old spreadsheet, filed as <b>{profileName}</b>&apos;s record. Not this
          cycle&apos;s sheet and not counted as this week&apos;s work — it is what stops
          you being handed postings you already applied to months ago.
        </p>
      </div>

      {note && <div className={note.bad ? "notice" : "notice ok"}>{note.text}</div>}

      {unfinished.length > 0 && (
        <div className="notice warn stack" style={{ gap: 8 }}>
          <b>{unfinished.length === 1 ? "An import" : `${unfinished.length} imports`} stopped part way.</b>
          {unfinished.map((record) => (
            <div key={record.id} className="row" style={{ gap: 10, flexWrap: "wrap" }}>
              <span style={{ flex: "1 1 240px" }}>
                <b>{record.filename || "sheet"}</b>{" "}
                <span className="muted">
                  — {count(record.cursor)} of {count(record.row_count)} rows,{" "}
                  {count(record.added)} added
                </span>
              </span>
              <button className="ghost" disabled={busy} onClick={() => write(record)}>
                Carry on
              </button>
            </div>
          ))}
        </div>
      )}

      {!current && (
        <>
          <label className="row" style={{ gap: 8, alignItems: "flex-start" }}>
            <input type="checkbox" checked={share} style={{ marginTop: 3 }}
                   onChange={(e) => setShare(e.target.checked)} />
            <span>
              <b>Offer these to the rest of the team</b>
              <p className="hint" style={{ marginTop: 2, maxWidth: 640 }}>
                A colleague who has never applied to one of these gets it on their
                others&apos; jobs list for the cycle that is open now. They go behind
                everything found this week, because they are older and some will be
                filled. Leave it off to file them as your record only.
              </p>
            </span>
          </label>

          <div className={hot ? "drop hot" : "drop"}
               onClick={() => fileInput.current?.click()}
               onDragOver={(e) => { e.preventDefault(); setHot(true); }}
               onDragLeave={() => setHot(false)}
               onDrop={(e) => { e.preventDefault(); setHot(false); read(e.dataTransfer.files[0]); }}>
            <div style={{ fontFamily: "var(--display)", fontWeight: 500, fontSize: 15 }}>
              {busy ? "Reading the sheet…" : "Drop your old sheet here, or click to choose"}
            </div>
            <div className="muted" style={{ marginTop: 5 }}>
              .xlsx, .xls or .csv. Handing in the same file twice is safe — the rows
              already on record are left alone and only what is missing is added.
            </div>
            <input ref={fileInput} type="file" accept=".xlsx,.xls,.csv,.tsv" hidden
                   onChange={(e) => read(e.target.files[0])} />
          </div>
        </>
      )}

      {current && (
        <div className="card pad stack" style={{ gap: 12 }}>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <b style={{ fontFamily: "var(--display)" }}>{current.filename || "Your sheet"}</b>
              <p className="muted" style={{ marginTop: 3 }}>
                {count(current.usable_count)} of {count(current.row_count)} rows carry
                enough to identify a posting.
              </p>
            </div>
            {!busy && (
              <button className="link" onClick={() => { setCurrent(null); setRun(null); }}>
                {done ? "Import another sheet" : "Put this one aside"}
              </button>
            )}
          </div>

          {/* The columns. Only movable before the first row is written: after
              that the mapping is what the rows already on record were read
              through, and changing it would make the tallies describe a sheet
              that was never imported. */}
          {!started && (
            <>
              <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))" }}>
                {Object.keys(FIELD_LABELS).map((key) => (
                  <div key={key}>
                    <label htmlFor={`imp-${key}`}>{FIELD_LABELS[key]}</label>
                    <select id={`imp-${key}`} value={current.mapping?.[key] || ""}
                            style={{ width: "100%", marginTop: 4,
                                     borderColor: key === "url" && !current.mapping?.url
                                       ? "var(--brick)" : undefined }}
                            onChange={(e) => remap(key, e.target.value)}>
                      <option value="">— not in my sheet —</option>
                      {(current.headers || []).map((h) => <option key={h} value={h}>{h}</option>)}
                    </select>
                  </div>
                ))}
              </div>
              {!current.mapping?.url && (
                <div className="notice">
                  No job link column is set. Matching falls back to client plus title,
                  which is less exact — two postings at one client with the same title
                  will be read as one.
                </div>
              )}
              {current.row_count > current.usable_count && (
                <p className="hint">
                  {count(current.row_count - current.usable_count)} rows carry no link,
                  no client and no title. Check the columns above before importing — if
                  they are still unreadable afterwards, they are blank rows and notes,
                  and nothing can file them.
                </p>
              )}
            </>
          )}

          {started && (
            <div className="stack" style={{ gap: 8 }}>
              <div className="bar" title={`${through} of ${rowCount} rows`}>
                <i style={{ width: `${rowCount ? (through / rowCount) * 100 : 0}%`,
                            background: done ? "var(--pine)" : "var(--a-line)" }} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", gap: 10 }}>
                <span className="muted">
                  {done ? "Finished." : `Row ${count(through)} of ${count(rowCount)}…`}
                </span>
                <Tally run={run || current} rowCount={rowCount} />
              </div>
            </div>
          )}

          <div className="row" style={{ gap: 10 }}>
            {!done && !busy && (
              <button onClick={() => write(current)}>
                {started
                  ? `Carry on from row ${count(through)}`
                  : `Import ${count(current.usable_count)} rows`}
              </button>
            )}
            {busy && started && (
              <button className="ghost" onClick={() => { stop.current = true; }}>
                Stop after this chunk
              </button>
            )}
            <label className="row" style={{ gap: 6 }}>
              <input type="checkbox" checked={!!current.share_with_team}
                     onChange={(e) => {
                       setCurrent({ ...current, share_with_team: e.target.checked });
                       setShared(current, e.target.checked);
                     }} />
              <span className="muted">offer these to the rest of the team</span>
            </label>
          </div>
        </div>
      )}

      {past.length > 0 && (
        <details className="more">
          <summary>Sheets you have imported ({past.length})</summary>
          <div className="card scroll stacks">
            <table>
              <thead>
                <tr>
                  <th>Sheet</th><th>When</th><th>Rows</th><th>Added</th>
                  <th>Already there</th><th>Shared</th><th />
                </tr>
              </thead>
              <tbody>
                {past.map((record) => (
                  <tr key={record.id}>
                    <td className="truncate" data-label="">
                      {record.filename || "sheet"}
                      {record.status !== "done" && (
                        <div style={{ fontSize: 11, color: "var(--warn-text)" }}>
                          stopped at row {count(record.cursor)}
                        </div>
                      )}
                    </td>
                    <td className="muted" data-label="When" style={{ whiteSpace: "nowrap", fontSize: 12 }}>
                      {record.created_at || "—"}
                    </td>
                    <td data-label="Rows">{count(record.row_count)}</td>
                    <td data-label="Added">{count(record.added)}</td>
                    <td className="muted" data-label="Already there">{count(record.already)}</td>
                    <td data-label="Shared">
                      <label className="row" style={{ gap: 5 }}>
                        <input type="checkbox" checked={!!record.share_with_team}
                               onChange={(e) => setShared(record, e.target.checked)} />
                        <span className="muted" style={{ fontSize: 12 }}>
                          {record.batch_id ? "on the team's lists" : "no cycle was open"}
                        </span>
                      </label>
                    </td>
                    <td data-label="">
                      <div className="row" style={{ gap: 8 }}>
                        {record.status !== "done" && (
                          <button className="ghost" disabled={busy}
                                  onClick={() => write(record)}>Carry on</button>
                        )}
                        <button className="link" onClick={() => forget(record)}>forget</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">
            Forgetting a sheet removes the file and its tallies. The applications it
            filed stay — they are {profileName}&apos;s record of work that was really
            done — but the postings stop being offered to colleagues.
          </p>
        </details>
      )}
    </section>
  );
}
