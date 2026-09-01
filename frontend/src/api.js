const KEY = "dispatch.token";

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

export const api = {
  login: (email, password) => request("/auth/login", { method: "POST", body: { email, password } }),
  me: () => request("/auth/me"),

  listUsers: () => request("/users"),
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
  jobRecord: ({ q = "", profileId = null, limit = 50, offset = 0 } = {}) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (profileId) params.set("profile_id", String(profileId));
    params.set("limit", String(limit));
    params.set("offset", String(offset));
    return request(`/jobs?${params.toString()}`);
  },

  // Take-homes and tests. Same shape as the diary and scoped the same way.
  assessments: (profileId) =>
    request(`/assessments${profileId ? `?profile_id=${profileId}` : ""}`),
  createAssessment: (payload) => request("/assessments", { method: "POST", body: payload }),
  updateAssessment: (id, payload) =>
    request(`/assessments/${id}`, { method: "PATCH", body: payload }),
  deleteAssessment: (id) => request(`/assessments/${id}`, { method: "DELETE" }),

  // Every conversation and take-home as a spreadsheet, scoped from the token
  // like the screens are. Used with `download`, not `request`.
  pipelinePath: (profileId) =>
    `/pipeline.xlsx${profileId ? `?profile_id=${profileId}` : ""}`,

  // A developer's own screen, and a manager looking at one.
  devDashboard: (batchId, dateFrom, dateTo) => request(`/dashboard/dev${query(batchId, dateFrom, dateTo)}`),
  developerDashboard: (userId, batchId, dateFrom, dateTo) =>
    request(`/dashboard/devs/${userId}${query(batchId, dateFrom, dateTo)}`),
  setStatus: (assignmentId, status) =>
    request(`/assignments/${assignmentId}`, { method: "PATCH", body: { status } }),
};
