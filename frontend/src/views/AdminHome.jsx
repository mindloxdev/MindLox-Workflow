import React, { useCallback, useEffect, useState } from "react";
import { api, download, safeUrl } from "../api.js";
import { sinceText } from "./widgets.jsx";

function Matrix({ names, rows }) {
  const offDiagonal = rows.flatMap((row, i) => row.filter((_, j) => i !== j));
  const peak = Math.max(1, ...offDiagonal);

  return (
    <div className="card scroll">
      <table className="matrix">
        <thead>
          <tr>
            <th />
            {names.map((n) => <th key={n}>{n}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={names[i]}>
              <td style={{ fontWeight: 500, whiteSpace: "nowrap" }}>{names[i]}</td>
              {row.map((value, j) => {
                const self = i === j;
                const heat = self ? 0 : Math.min(0.88, value / peak);
                return (
                  <td key={j} style={{
                    background: self ? "var(--paper)" : `rgba(158,59,44,${heat * 0.85})`,
                    color: self ? "var(--slate)" : heat > 0.5 ? "#fff" : "var(--ink)",
                    fontWeight: self ? 400 : 500,
                  }}>{value}</td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AdminHome() {
  const [batches, setBatches] = useState([]);
  const [current, setCurrent] = useState(null);
  const [detail, setDetail] = useState(null);
  const [report, setReport] = useState(null);
  const [note, setNote] = useState(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState({
    name: "", quota: 40, mode: "cover", one_per_client: false, auto_build_minutes: 10,
  });

  // Rebuilds happen on the server whether or not anyone is looking, so the
  // screen refreshes itself to stay honest about what the lists contain.
  useEffect(() => {
    if (!current) return undefined;
    const tick = setInterval(() => {
      api.report(current).then(setReport).catch(() => {});
      api.getBatch(current).then(setDetail).catch(() => {});
    }, 30000);
    return () => clearInterval(tick);
  }, [current]);

  const refresh = useCallback(async (selectId) => {
    const rows = await api.listBatches();
    setBatches(rows);
    const pick = selectId || current || (rows[0] && rows[0].id);
    if (pick) setCurrent(pick);
  }, [current]);

  useEffect(() => { refresh().catch((e) => setNote({ bad: true, text: e.message })); }, []);

  useEffect(() => {
    if (!current) return;
    setReport(null);
    api.getBatch(current).then(setDetail).catch(() => setDetail(null));
    api.report(current).then(setReport).catch(() => setReport(null));
  }, [current]);

  const create = async () => {
    setBusy(true);
    setNote(null);
    try {
      const batch = await api.createBatch({
        name: draft.name.trim() || `Cycle ${new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short" })}`,
        quota: Number(draft.quota) || 40,
        mode: draft.mode,
        one_per_client: draft.one_per_client,
        auto_build_minutes: Number(draft.auto_build_minutes),
      });
      setDraft({ ...draft, name: "", quota: 40, one_per_client: false });
      await refresh(batch.id);
      setNote({
        text: batch.auto_build_minutes
          ? `${batch.name} is open. Lists rebuild every ${batch.auto_build_minutes} minutes on their own — you do not need to come back.`
          : `${batch.name} is open. You will need to build the lists yourself.`,
      });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const compute = async () => {
    setBusy(true);
    setNote(null);
    try {
      const data = await api.compute(current);
      setReport(data);
      await refresh(current);
      const detailData = await api.getBatch(current);
      setDetail(detailData);
      const full = await api.report(current).catch(() => data);
      setReport(full);
      setNote({ text: `Lists built. ${data.report["Jobs put on a list"]} jobs went out across ${data.participants.length} profiles.` });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const finish = async () => {
    if (!window.confirm(
      "Close this cycle? No more sheets are accepted and the lists stop rebuilding. " +
      "Everyone keeps what they already have.")) return;
    setBusy(true);
    try {
      await api.closeBatch(current);
      await refresh(current);
      setDetail(await api.getBatch(current));
      setNote({ text: "Cycle closed. Open a new one when the next round starts." });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const reopen = async () => {
    setBusy(true);
    try {
      await api.reopenBatch(current);
      await refresh(current);
      setDetail(await api.getBatch(current));
      setNote({ text: "Cycle reopened. Sheets are accepted again and rebuilding resumes." });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const handedIn = detail?.uploads?.length || 0;

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>Batches</h1>
          <p className="muted" style={{ marginTop: 3 }}>
            Open a cycle, wait for everyone's sheet, then build the lists.
          </p>
        </div>
        {batches.length > 0 && (
          <label>
            Viewing&nbsp;
            <select value={current || ""} onChange={(e) => setCurrent(Number(e.target.value))}>
              {batches.map((b) => (
                <option key={b.id} value={b.id}>{b.name} · {b.status}</option>
              ))}
            </select>
          </label>
        )}
      </div>

      {note && <div className={note.bad ? "notice" : "notice ok"}>{note.text}</div>}

      <section className="card pad">
        <h2>Start a new cycle</h2>
        <div className="row" style={{ marginTop: 12 }}>
          <input placeholder="Name, e.g. Week 33" value={draft.name} style={{ minWidth: 200 }}
                 onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          <label>
            Cap per profile
            <input type="number" min="1" max="1000" value={draft.quota} style={{ width: 80 }}
                   onChange={(e) => setDraft({ ...draft, quota: e.target.value })} />
          </label>
          <label>
            <input type="checkbox" checked={draft.one_per_client}
                   onChange={(e) => setDraft({ ...draft, one_per_client: e.target.checked })} />
            One job per client, per profile
          </label>
          <label>
            Rebuild lists
            <select value={draft.auto_build_minutes} style={{ marginLeft: 6 }}
                    onChange={(e) => setDraft({ ...draft, auto_build_minutes: e.target.value })}>
              <option value={5}>every 5 minutes</option>
              <option value={10}>every 10 minutes</option>
              <option value={15}>every 15 minutes</option>
              <option value={30}>every 30 minutes</option>
              <option value={0}>only when I ask</option>
            </select>
          </label>
          <button onClick={create} disabled={busy}>Open cycle</button>
        </div>

        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", marginTop: 14 }}>
          {[
            { key: "cover", title: "Give every profile what it has not tried",
              blurb: "The sheets are pooled, then each profile gets back everything it has never applied to. Two profiles are two candidates, so both may go for the same job." },
            { key: "split", title: "Split the pool, no two profiles share",
              blurb: "Every job goes to exactly one profile. Use this when the profiles are really one identity and a second application would look like a repeat." },
          ].map((option) => (
            <label key={option.key} className="card pad" style={{
              display: "block", cursor: "pointer",
              borderColor: draft.mode === option.key ? "var(--petrol)" : "var(--rule)",
              borderWidth: draft.mode === option.key ? 2 : 1,
            }}>
              <span className="row" style={{ gap: 8, alignItems: "flex-start" }}>
                <input type="radio" name="mode" value={option.key} checked={draft.mode === option.key}
                       onChange={() => setDraft({ ...draft, mode: option.key })} />
                <span>
                  <b style={{ fontFamily: "var(--display)" }}>{option.title}</b>
                  <span className="muted" style={{ display: "block", marginTop: 4 }}>{option.blurb}</span>
                </span>
              </span>
            </label>
          ))}
        </div>

        <p className="hint">
              Stops one profile bidding on four jobs from the same buyer.
            </p>
      </section>

      {detail && (
        <section className="stack" style={{ gap: 10 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2>Sheets handed in · {detail.name}</h2>
            <div className="row" style={{ gap: 8 }}>
              <span className="pill">
                {detail.mode === "split" ? "split the pool" : "cover every profile"}
              </span>
              <span className={detail.status === "open" ? "pill" : "pill on"}>
                {detail.status === "open" ? "open" : "closed"}
              </span>
              <button className="ghost" onClick={compute} disabled={busy || handedIn < 2}>
                {busy ? "Working…" : "Build now"}
              </button>
              {detail.status === "open"
                ? <button onClick={finish} disabled={busy}>Close cycle</button>
                : <button className="ghost" onClick={reopen} disabled={busy}>Reopen</button>}
            </div>
          </div>

          {detail.status === "open" && detail.auto_build_minutes > 0 && (
            <div className="notice ok">
              <b>Building itself.</b> The lists rebuild every {detail.auto_build_minutes} minutes
              while this cycle is open, so whatever your team has logged is already reflected.
              {detail.last_built_at
                ? ` Last built ${sinceText(detail.last_built_at)}.`
                : handedIn < 2
                  ? " Nothing built yet — it starts once two profiles have handed in."
                  : " First build is due within a minute."}
              {" "}Close the cycle when the week is done.
            </div>
          )}

          {detail.status === "open" && !detail.auto_build_minutes && (
            <div className="notice">
              This cycle only builds when you press <b>Build now</b>.
              {detail.last_built_at && ` Last built ${sinceText(detail.last_built_at)}.`}
            </div>
          )}

          {handedIn < 2 && (
            <div className="notice">
              {handedIn} profile{handedIn === 1 ? " has" : "s have"} handed in. At least two sheets
              are needed before anything can be compared.
            </div>
          )}

          <div className="card scroll">
            <table>
              <thead>
                <tr><th>Profile</th><th>Resume</th><th>Run by</th><th>File</th><th>Rows</th><th>Link column</th></tr>
              </thead>
              <tbody>
                {detail.uploads.map((u) => (
                  <tr key={u.id}>
                    <td style={{ fontWeight: 500 }}>{u.profile}</td>
                    <td className="muted">{u.headline || "—"}</td>
                    <td>{u.person}</td>
                    <td className="mono truncate" style={{ fontSize: 12 }}>{u.filename}</td>
                    <td className="mono">{u.row_count}</td>
                    <td>
                      {u.mapping?.url
                        ? <span className="pill on">{u.mapping.url}</span>
                        : <span className="pill off">falling back to client + title</span>}
                    </td>
                  </tr>
                ))}
                {!detail.uploads.length && (
                  <tr><td colSpan={6} className="muted">Nobody has handed in yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {report?.report && Object.keys(report.report).length > 0 && (
        <section className="stack" style={{ gap: 14 }}>
          <h2>What the comparison found</h2>
          <div className="stats">
            {Object.entries(report.report).map(([label, value]) => (
              <div className="stat" key={label}>
                <b style={{ color: /Duplicate|2 or more/.test(label) ? "var(--brick)" : "var(--ink)" }}>{value}</b>
                <span>{label}</span>
              </div>
            ))}
          </div>

          {report.matrix?.names?.length > 1 && (
            <div>
              <h3>Which profiles are stepping on each other</h3>
              <p className="hint" style={{ marginTop: 3 }}>
            Jobs both profiles applied to. Dark means near-identical searches.
          </p>
              <Matrix names={report.matrix.names} rows={report.matrix.rows} />
            </div>
          )}

          <div className="row" style={{ justifyContent: "space-between" }}>
            <h3>Lists going out</h3>
            <button className="go" onClick={() =>
              download(`/batches/${current}/report.xlsx`, "dispatch.xlsx")
                .catch((err) => setNote({ bad: true, text: err.message }))}>
              Download everything as one workbook
            </button>
          </div>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(180px,1fr))" }}>
            {report.participants.map((p) => (
              <div className="card pad" key={p.id} style={{ borderTop: `3px solid ${p.assigned ? "var(--pine)" : "var(--rule)"}` }}>
                <div style={{ fontFamily: "var(--display)", fontWeight: 600 }}>{p.name}</div>
                <div className="muted" style={{ marginTop: 2 }}>{p.headline || "—"}</div>
                <div className="mono" style={{ fontSize: 25, fontWeight: 500, marginTop: 6 }}>{p.assigned}</div>
                <div className="muted">
                  new jobs{p.person ? ` · ${p.person}` : ""}
                </div>
              </div>
            ))}
          </div>

          {report.collisions?.length > 0 && (
            <div>
              <h3>Jobs more than one profile already applied to</h3>
              <p className="muted" style={{ margin: "3px 0 9px" }}>
                Two of your profiles reached the same client this cycle. Showing the
                {" "}{Math.min(report.collisions.length, 50)} worst.
              </p>
              <div className="card scroll">
                <table>
                  <thead>
                    <tr><th>Job</th><th>Client</th><th>Applied by</th></tr>
                  </thead>
                  <tbody>
                    {report.collisions.slice(0, 50).map((c, i) => (
                      <tr key={i}>
                        <td className="truncate">
                          {safeUrl(c.url)
                            ? <a href={safeUrl(c.url)} target="_blank" rel="noreferrer noopener">{c.title || c.url}</a>
                            : (c.title || "—")}
                        </td>
                        <td>{c.company || "—"}</td>
                        <td style={{ color: "var(--brick)", fontWeight: 500 }}>{c.applied_by.join(", ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
