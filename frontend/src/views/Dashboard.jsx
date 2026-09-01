import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import PersonDashboard from "./PersonDashboard.jsx";
import { DateRange, Loading } from "./widgets.jsx";

/** A BD's own dashboard.
 *
 * Fetches; the screen itself is PersonDashboard, which a manager renders too.
 * If the manager has not opened this person's dashboard the server refuses the
 * request, and that refusal is what is shown — the app does not pretend the
 * screen is loading, or that it is empty.
 */
export default function Dashboard({ onOpenWork }) {
  const [data, setData] = useState(null);
  const [batchId, setBatchId] = useState(null);
  const [dateRange, setDateRange] = useState({ dateFrom: "", dateTo: "" });
  const [board, setBoard] = useState(null);
  const [showBoard, setShowBoard] = useState(false);
  const [error, setError] = useState("");
  const [shut, setShut] = useState(false);

  const load = useCallback(async (id) => {
    try {
      const next = await api.dashboard(id, dateRange.dateFrom, dateRange.dateTo);
      setData(next);
      if (!id && next.batch) setBatchId(next.batch.id);
      setError("");
      setShut(false);
    } catch (err) {
      if (/has not opened/i.test(err.message)) setShut(true);
      else setError(err.message);
    }
  }, [dateRange]);

  useEffect(() => { load(batchId); }, [batchId, load]);

  // The lists rebuild on the server whether or not anyone is looking, so these
  // numbers go stale on their own. Pick the new ones up rather than showing a
  // figure that quietly stopped being true ten minutes ago.
  useEffect(() => {
    if (shut) return undefined;
    const tick = setInterval(() => load(batchId), 60000);
    return () => clearInterval(tick);
  }, [batchId, load, shut]);

  useEffect(() => {
    if (!showBoard || !data?.team_visible) return;
    api.teamBoard(batchId).then(setBoard).catch((err) => setError(err.message));
  }, [showBoard, batchId, data?.team_visible]);

  if (shut) {
    return (
      <div className="stack">
        <h1>Your dashboard</h1>
        <div className="notice">
          Your manager has not opened your dashboard yet. Until they do, your work is
          unaffected — <b>My work</b> has your list and the sheet you hand in, exactly as before.
        </div>
      </div>
    );
  }

  if (error && !data) return <div className="notice">{error}</div>;
  if (!data) return <Loading lines={4} figures />;

  return (
    <PersonDashboard
      data={data}
      batchId={batchId}
      onBatchChange={setBatchId}
      dateRange={dateRange}
      onDateRangeChange={setDateRange}
      onOpenWork={onOpenWork}
      board={board}
      showBoard={showBoard}
      onToggleBoard={() => setShowBoard((on) => !on)}
      error={error}
    />
  );
}
