import React, { useEffect, useState } from "react";
import { api, safeUrl } from "../api.js";
import { Loading } from "./widgets.jsx";

/** The jobs behind a skipped count, in the words they were turned down in.
 *
 * A skip is the one decision on a BD's screen that destroys work — the job
 * leaves that profile and no later cycle offers it again — so a count of them
 * that could not be opened was the least accountable number in the app. A BD
 * could not read their own reasoning back at the end of a week, and a manager
 * reading "47 skipped" on somebody's row could not tell a profile being
 * protected from a week of good postings thrown away without going to find a
 * different screen.
 *
 * Its own file rather than a widget, because it fetches: `widgets.jsx` is kept
 * clear of the api module on purpose, and three screens each writing their own
 * request for the same list is how three screens end up disagreeing about what
 * the number meant.
 *
 * Scoped the way the count that opened it is scoped — one profile when one is
 * named, and the same dates — so the list adds up to the number that was
 * pressed. A list that quietly showed the whole cycle under a figure counting
 * one morning would be worse than no list at all.
 */
export default function Skipped({ batchId, profileId = null, dateFrom = "", dateTo = "",
                                  since = "", until = "", showProfile = false }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!batchId) return undefined;
    // `live` guards against the answer to a request nobody is waiting for any
    // more landing on top of a newer one — the panel is opened and closed, and
    // the cycle and dates change underneath it.
    let live = true;
    setData(null);
    setError("");
    api.skipped(batchId, { profileId, dateFrom, dateTo, since, until })
      .then((next) => { if (live) setData(next); })
      .catch((err) => { if (live) setError(err.message); });
    return () => { live = false; };
  }, [batchId, profileId, dateFrom, dateTo, since, until]);

  if (error) return <div className="notice">{error}</div>;
  if (!data) return <Loading lines={2} />;
  if (!data.rows.length) {
    return (
      <p className="hint" style={{ margin: 0 }}>
        Nothing was skipped here. Everything handed over was either applied for or
        is still waiting.
      </p>
    );
  }

  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="card scroll stacks">
        <table>
          <thead>
            <tr>
              <th>Job</th>
              <th>Company</th>
              {showProfile && <th>Applied as</th>}
              <th>Why it was skipped</th>
              <th>When</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.id}>
                <td className="truncate" data-label="" style={{ maxWidth: 260 }}>
                  {safeUrl(row.url)
                    ? <a href={safeUrl(row.url)} target="_blank" rel="noreferrer noopener">
                        {row.title || row.url}
                      </a>
                    : (row.title || "—")}
                </td>
                <td data-label="Company">{row.company || "—"}</td>
                {showProfile && (
                  <td data-label="Applied as">
                    <b>{row.profile}</b>
                    {row.person && <span className="muted"> · {row.person}</span>}
                  </td>
                )}
                <td data-label="Why it was skipped" style={{ maxWidth: 340 }}>
                  {/* Said out loud rather than left blank. A row with no reason
                      is one skipped before the app asked for one, and that is a
                      different thing from a reason nobody could think of. */}
                  {row.reason || <span className="muted">no reason recorded</span>}
                </td>
                <td className="muted" data-label="When"
                    style={{ whiteSpace: "nowrap" }}>{row.when || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.total > data.rows.length && (
        <p className="hint" style={{ margin: 0 }}>Showing {data.rows.length} of {data.total}.</p>
      )}
      <p className="hint" style={{ margin: 0, maxWidth: 700 }}>
        Worth reading together rather than one at a time. A run of the same reason
        against one profile is usually something about the searches feeding it,
        not about the postings.
      </p>
    </div>
  );
}
