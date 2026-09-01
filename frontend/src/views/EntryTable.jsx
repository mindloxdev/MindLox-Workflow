import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Loading } from "./widgets.jsx";

const COLUMNS = [
  { key: "url", label: "Job link", width: "26%", hint: "https://…" },
  { key: "title", label: "Job title", width: "20%", hint: "" },
  { key: "company", label: "Client", width: "14%", hint: "" },
  // Where the posting is written out, when that is not the apply link. The
  // apply link is usually dead three weeks later — an expired posting
  // redirects to a board's home page and takes the wording with it — and this
  // is what a BD still has when the client finally replies.
  { key: "description_url", label: "Description link", width: "20%", hint: "optional" },
  { key: "platform", label: "Platform", width: "10%", hint: "" },
  { key: "date", label: "Applied on", width: "10%", hint: "" },
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
const blankRow = () => ({ url: "", title: "", company: "", description_url: "",
                          platform: "", date: stampNow() });
const isEmpty = (row) => IDENTIFYING.every((key) => !String(row[key] || "").trim());

/** Rows typed in by hand, saved as this profile's sheet for the cycle. */
export default function EntryTable({ batchId, profileId, profileName, onSaved }) {
  const [rows, setRows] = useState([]);
  const [state, setState] = useState("loading");   // loading | idle | saving | saved | error
  const [error, setError] = useState("");
  const lastCell = useRef(null);
  const lastSaved = useRef(null);

  useEffect(() => {
    let live = true;
    setState("loading");
    api.listEntries(batchId, profileId)
      .then((data) => {
        if (!live) return;
        setRows(data.rows.length ? data.rows : [blankRow()]);
        lastSaved.current = JSON.stringify(data.rows);
        setState("idle");
      })
      .catch((err) => { if (live) { setError(err.message); setState("error"); } });
    return () => { live = false; };
  }, [batchId, profileId]);

  const save = useCallback(async (next) => {
    // Blur fires whenever focus moves, so most calls have nothing new to say.
    const payload = next.filter((r) => !isEmpty(r));
    const signature = JSON.stringify(payload);
    if (signature === lastSaved.current) return;

    setState("saving");
    setError("");
    try {
      const result = await api.saveEntries(batchId, profileId, payload);
      lastSaved.current = signature;
      setState("saved");
      onSaved?.(result);
    } catch (err) {
      setError(err.message);
      setState("error");
    }
  }, [batchId, profileId, onSaved]);

  const edit = (index, key, value) => {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, [key]: value } : row)));
    setState("idle");
  };

  const addRow = () => {
    setRows((current) => {
      lastCell.current = current.length;
      return [...current, blankRow()];
    });
    setState("idle");
  };

  const removeRow = (index) => {
    setRows((current) => {
      const next = current.filter((_, i) => i !== index);
      const safe = next.length ? next : [blankRow()];
      save(safe);
      return safe;
    });
  };

  // Focus the first cell of a freshly added row so you can just start typing.
  useEffect(() => {
    if (lastCell.current === null) return;
    document.getElementById(`cell-${lastCell.current}-url`)?.focus();
    lastCell.current = null;
  }, [rows.length]);

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
        if (!next[target]) next[target] = blankRow();
        else next[target] = { ...next[target] };
        cells.forEach((value, c) => {
          const column = COLUMNS[startColumn + c];
          if (column) next[target][column.key] = value.trim();
        });
        // A pasted block usually carries no date, or an empty trailing cell.
        if (!next[target].date) next[target].date = stampNow();
      });
      save(next);
      return next;
    });
  };

  const filled = rows.filter((r) => !isEmpty(r)).length;
  const noLink = rows.filter((r) => !isEmpty(r) && !String(r.url || "").trim()).length;

  if (state === "loading") return <Loading lines={3} />;

  return (
    <div className="stack" style={{ gap: 10 }}>
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
                {COLUMNS.map((c) => (
                  <td key={c.key} style={{ padding: 3 }}>
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
                      onBlur={() => save(rows)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && index === rows.length - 1) addRow();
                      }}
                    />
                  </td>
                ))}
                <td style={{ textAlign: "center", padding: 3 }}>
                  <button className="link" title="Remove this row"
                          onClick={() => removeRow(index)}>&times;</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="row" style={{ gap: 10 }}>
          <button onClick={addRow}>+ New entry</button>
          <span className="muted">
            {filled} {filled === 1 ? "job" : "jobs"} recorded for {profileName}
          </span>
        </div>
        <span className="muted">
          {state === "saving" && "Saving…"}
          {state === "saved" && "Saved"}
          {state === "error" && <span style={{ color: "var(--brick)" }}>{error}</span>}
        </span>
      </div>

      {noLink > 0 && (
        <div className="notice">
          {noLink} {noLink === 1 ? "row has" : "rows have"} no job link. Those can only be
          matched on client plus title, so the same posting found by someone else may not be
          recognised. Paste the link where you can.
        </div>
      )}

      <p className="hint" style={{ marginTop: 3 }}>
        <b>Enter</b> on the last row adds another. Paste a block straight from
        Excel and it fills across.
      </p>
    </div>
  );
}
