const KEY = "dispatch.token";

/** What actually happened to a posting when an entry was deleted.
 *
 * Three outcomes and they are not the same news. It was deleted; it was kept
 * because a colleague also applied and their record is not this person's to
 * remove; or it was kept because a client replied to it, which is the rarest
 * row in the system and outlives the application that earned it.
 */
export function deletedLabel(result, what) {
  if (result?.job_deleted) return `${what} was deleted.`;
  if (result?.kept_for_replies > 0) {
    return `${what} was withdrawn. The posting stays — a client replied to it.`;
  }
  return `${what} was withdrawn. A colleague still holds the posting.`;
}

export function getToken() {
  return sessionStorage.getItem(KEY) || "";
}

export function setToken(value) {
  if (value) sessionStorage.setItem(KEY, value);
  else sessionStorage.removeItem(KEY);
}

async function request(path, { method = "GET", body, form } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body) headers["Content-Type"] = "application/json";

  const response = await fetch(`/api${path}`, {
    method,
    headers,
    body: form ? form : body ? JSON.stringify(body) : undefined,
  });

  if (response.status === 401) {
    setToken("");
    window.dispatchEvent(new Event("dispatch:signed-out"));
    throw new Error("Your session ended. Sign in again.");
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (data.detail) message = typeof data.detail === "string" ? data.detail : message;
    } catch {
      /* response had no JSON body */
    }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

/** Only ever put an http(s) link in an href.
 *
 * Job links come out of spreadsheets other people typed, and the backend is
 * not the last line of defence — a `javascript:` href would run in this app's
 * own origin, with the signed-in token sitting in sessionStorage.
 */
export function safeUrl(value) {
  return /^https?:\/\//i.test(value || "") ? value : "";
}

/** Trigger a browser download for an authenticated endpoint. */
export async function download(path, fallbackName) {
  const response = await fetch(`/api${path}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!response.ok) {
    let message = "That file is not ready yet.";
    try {
      const data = await response.json();
      if (data.detail) message = data.detail;
    } catch { /* not JSON */ }
    throw new Error(message);
  }
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = match ? match[1] : fallbackName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

const query = (batchId, dateFrom, dateTo) => {
  const params = new URLSearchParams();
  if (batchId) params.set("batch_id", batchId);
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  const text = params.toString();
  return text ? `?${text}` : "";
};

const crmQuery = ({ dateFrom, dateTo, status, q, sort, page, perPage }) => {
  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  if (status) params.set("status", status);
  if (q) params.set("q", q);
  if (sort) params.set("sort", sort);
  if (page && page > 1) params.set("page", String(page));
  if (perPage) params.set("per_page", String(perPage));
  const text = params.toString();
  return text ? `?${text}` : "";
};

export const api = {
  login: (email, password) => request("/auth/login", { method: "POST", body: { email, password } }),
  me: () => request("/auth/me"),

  listUsers: () => request("/users"),
  listDevelopers: () => request("/developers"),
  createUser: (payload) => request("/users", { method: "POST", body: payload }),
  updateUser: (id, payload) => request(`/users/${id}`, { method: "PATCH", body: payload }),
  deactivateUser: (id) => request(`/users/${id}`, { method: "DELETE" }),

  listProfiles: () => request("/profiles"),
  getProfile: (id) => request(`/profiles/${id}`),
  createProfile: (payload) => request("/profiles", { method: "POST", body: payload }),
  updateProfile: (id, payload) => request(`/profiles/${id}`, { method: "PATCH", body: payload }),
  retireProfile: (id) => request(`/profiles/${id}`, { method: "DELETE" }),

  listBatches: () => request("/batches"),
  createBatch: (payload) => request("/batches", { method: "POST", body: payload }),
  getBatch: (id) => request(`/batches/${id}`),
  compute: (id) => request(`/batches/${id}/compute`, { method: "POST" }),
  closeBatch: (id) => request(`/batches/${id}/close`, { method: "POST" }),
  reopenBatch: (id) => request(`/batches/${id}/reopen`, { method: "POST" }),
  report: (id) => request(`/batches/${id}/report`),

  // The cycle clock. `minutes` sets the whole budget and starts it from now;
  // `add_minutes` moves the budget without touching the start, and may be
  // negative. A budget of 0 takes the clock away.
  setCycleTimer: (id, payload) =>
    request(`/batches/${id}/timer`, { method: "PUT", body: payload }),
  // What each profile did inside the window the clock measured. Manager only.
  timerReport: (id) => request(`/batches/${id}/timer-report`),

  upload: (batchId, profileId, file) => {
    const form = new FormData();
    form.append("profile_id", profileId);
    form.append("file", file);
    return request(`/batches/${batchId}/uploads`, { method: "POST", form });
  },
  setMapping: (uploadId, mapping) =>
    request(`/uploads/${uploadId}/mapping`, { method: "PATCH", body: { mapping } }),
  deleteUpload: (uploadId) => request(`/uploads/${uploadId}`, { method: "DELETE" }),

  listEntries: (batchId, profileId) =>
    request(`/batches/${batchId}/profiles/${profileId}/entries`),
  saveEntries: (batchId, profileId, rows) =>
    request(`/batches/${batchId}/profiles/${profileId}/entries`, { method: "PUT", body: { rows } }),

  settings: () => request("/settings"),
  saveSettings: (payload) => request("/settings", { method: "PATCH", body: payload }),

  // A cycle is optional everywhere below: leave it off and the server opens on
  // the newest cycle still running.
  dashboard: (batchId, dateFrom, dateTo) => request(`/dashboard/me${query(batchId, dateFrom, dateTo)}`),
  teamBoard: (batchId) => request(`/dashboard/team${query(batchId)}`),
  overview: (batchId, dateFrom, dateTo) => request(`/dashboard/overview${query(batchId, dateFrom, dateTo)}`),
  // One person's dashboard as they would see it. Manager only.
  personDashboard: (userId, batchId, dateFrom, dateTo) =>
    request(`/dashboard/people/${userId}${query(batchId, dateFrom, dateTo)}`),
  profileDetail: (profileId, batchId, dateFrom, dateTo) =>
    request(`/dashboard/profiles/${profileId}${query(batchId, dateFrom, dateTo)}`),

  mySheets: (batchId) => request(`/batches/${batchId}/my-sheets`),

  // What was skipped in a cycle, and why. Scoped exactly like the count that
  // opens it — one profile when one is named, and the same dates — or the list
  // would not add up to the number that was pressed.
  skipped: (batchId, { profileId = null, dateFrom = "", dateTo = "",
                       since = "", until = "" } = {}) => {
    const params = new URLSearchParams();
    if (profileId) params.set("profile_id", String(profileId));
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    // The cycle clock counts an exact window rather than whole days.
    if (since) params.set("since", since);
    if (until) params.set("until", until);
    const text = params.toString();
    return request(`/batches/${batchId}/skipped${text ? `?${text}` : ""}`);
  },

  // Clients. Manager only, and checked on the server — the tab being absent
  // for everybody else is a courtesy, not the control.
  clients: ({ dateFrom = "", dateTo = "", status = "", q = "",
              sort = "last_activity", page = 1, perPage = 50 } = {}) =>
    request(`/crm/clients${crmQuery({ dateFrom, dateTo, status, q, sort, page, perPage })}`),
  client: (key) => request(`/crm/clients/${encodeURIComponent(key)}`),
  saveClientNote: (key, payload) =>
    request(`/crm/clients/${encodeURIComponent(key)}/note`,
            { method: "PUT", body: payload }),
  // Used with `download`, not `request`.
  clientsExportPath: ({ dateFrom = "", dateTo = "", status = "", q = "" } = {}) =>
    `/crm/export.xlsx${crmQuery({ dateFrom, dateTo, status, q })}`,

  // Interviews. Scoped on the server from the token: a BD sees the profiles
  // they run, a developer the ones they are sold under, a manager everything.
  // Times go up and come back on the team's clock — see models.from_working.
  interviews: (profileId, dateFrom, dateTo) => {
    const params = new URLSearchParams();
    if (profileId) params.set("profile_id", profileId);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    const text = params.toString();
    return request(`/interviews${text ? `?${text}` : ""}`);
  },
  createInterview: (payload) => request("/interviews", { method: "POST", body: payload }),
  updateInterview: (id, payload) =>
    request(`/interviews/${id}`, { method: "PATCH", body: payload }),
  deleteInterview: (id) => request(`/interviews/${id}`, { method: "DELETE" }),
  // Book the round after one that was cleared. The client, the role and the
  // posting come across from it, and the round before is marked passed —
  // booking the next one is what says the last one went well.
  nextRound: (id, payload = {}) =>
    request(`/interviews/${id}/next-round`, { method: "POST", body: payload }),

  // Every job applied for, all-time and searchable. Not scoped to a cycle: a
  // client's reply arrives long after the cycle that earned it closed.
  jobRecord: ({ q = "", profileId = null, dateFrom = "", dateTo = "", limit = 50, offset = 0 } = {}) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (profileId) params.set("profile_id", String(profileId));
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    params.set("limit", String(limit));
    params.set("offset", String(offset));
    return request(`/jobs?${params.toString()}`);
  },

  // Assessments. Same shape as the diary and scoped the same way.
  assessments: (profileId) =>
    request(`/assessments${profileId ? `?profile_id=${profileId}` : ""}`),
  createAssessment: (payload) => request("/assessments", { method: "POST", body: payload }),
  updateAssessment: (id, payload) =>
    request(`/assessments/${id}`, { method: "PATCH", body: payload }),
  deleteAssessment: (id) => request(`/assessments/${id}`, { method: "DELETE" }),

  // Every conversation and assessment as a spreadsheet, scoped from the token
  // like the screens are. Used with `download`, not `request`.
  pipelinePath: (profileId) =>
    `/pipeline.xlsx${profileId ? `?profile_id=${profileId}` : ""}`,

  // A developer's own screen, and a manager looking at one.
  devDashboard: (batchId, dateFrom, dateTo) => request(`/dashboard/dev${query(batchId, dateFrom, dateTo)}`),
  developerDashboard: (userId, batchId, dateFrom, dateTo) =>
    request(`/dashboard/devs/${userId}${query(batchId, dateFrom, dateTo)}`),
  // `reason` is required by the server when the status is "skipped" and
  // ignored otherwise. A skip retires the job from this profile for good, so
  // the manager gets to see why rather than only how many.
  // `everyProfile` turns it down for every profile this person runs, not only
  // the one on screen. Off by default: two profiles are two candidates, and a
  // job wrong for one market is often right for the other.
  setStatus: (assignmentId, status, reason = "", everyProfile = false) =>
    request(`/assignments/${assignmentId}`,
            { method: "PATCH", body: { status, reason, every_profile: everyProfile } }),

  // Has this posting been applied to before? Asked as the job link is typed,
  // before the row is saved. Matched on the fingerprint, so the same job pasted
  // with a tracking parameter still comes back as the same job.
  checkDuplicate: ({ url = "", title = "", company = "", profileId = null } = {}) => {
    const params = new URLSearchParams();
    if (url) params.set("url", url);
    if (title) params.set("title", title);
    if (company) params.set("company", company);
    if (profileId) params.set("profile_id", String(profileId));
    return request(`/jobs/check?${params.toString()}`);
  },

  // Correcting a posting corrects it for everyone holding it — there is one
  // row per job — so the server allows it only to whoever first logged it.
  editJob: (jobId, payload) =>
    request(`/jobs/${jobId}`, { method: "PATCH", body: payload }),

  // Delete one profile's entry. The posting goes with it unless somebody else
  // has applied to it, or a client replied to it — see deletedLabel.
  deleteEntry: (jobId, profileId) =>
    request(`/jobs/${jobId}/profiles/${profileId}`, { method: "DELETE" }),
};
