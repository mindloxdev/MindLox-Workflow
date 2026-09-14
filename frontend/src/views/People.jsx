import React, { useEffect, useState } from "react";
import { api, safeUrl } from "../api.js";
import { Availability } from "./widgets.jsx";

const BLANK_PERSON = { name: "", email: "", password: "", role: "bd" };
const BLANK_PROFILE = {
  name: "",
  headline: "",
  platform: "",
  user_id: "",
  dev_user_id: "",
  email: "",
  resume_url: "",
};

const ROLE_LABELS = {
  admin: "manager",
  bd: "business development",
  dev: "developer",
};

const HEADLINE_OPTIONS = [
  "",
  "VA",
  "AI Engineer",
  "Accounts Receivable",
  "Customer Service",
  "RCM Analyst",
];

const PLATFORM_OPTIONS = [
  "",
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

/* One of the two lists a profile sits on once it is off the working screens.
   Both are recoveries and both read the same, so they are one component and
   differ only in what they are called and what the hint explains. Neither is
   drawn at all when it is empty: a manager who has never switched anything off
   should not be told about a list of nothing. */
function OffList({ title, rows, hint, busy, onEnable }) {
  if (!rows.length) return null;
  return (
    <section className="card pad">
      <h2>{title}</h2>
      <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>{hint}</p>
      <div className="scroll" style={{ marginTop: 12 }}>
        <table>
          <thead>
            <tr><th>Profile</th><th>Headline</th><th>Was run by</th><th /></tr>
          </thead>
          <tbody>
            {rows.map((item) => (
              <tr key={item.id}>
                <td style={{ fontWeight: 500 }}>
                  {item.name}
                  {item.platform && (
                    <div className="muted" style={{ fontSize: 11 }}>{item.platform}</div>
                  )}
                </td>
                <td>{item.headline || <span className="muted">—</span>}</td>
                <td>{item.owner || <span className="muted">nobody</span>}</td>
                <td style={{ textAlign: "right" }}>
                  <button disabled={busy} onClick={() => onEnable(item)}>Enable</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function People() {
  const [people, setPeople] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [disabled, setDisabled] = useState([]);
  const [deleted, setDeleted] = useState([]);
  // Which person's row is open for editing, and the draft of it. One at a time:
  // handing a seat over is deliberate work, not something to do to four rows at
  // once and then wonder which took.
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState(null);
  const [person, setPerson] = useState(BLANK_PERSON);
  const [profile, setProfile] = useState(BLANK_PROFILE);
  const [note, setNote] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      // The two recovery lists are aids, not the screen. If either fails — an
      // older server, a role that may not ask — the rest still loads.
      const [users, identities, off, gone] = await Promise.all([
        api.listUsers(),
        api.listProfiles(),
        api.listProfilesInState("disabled").catch(() => []),
        api.listProfilesInState("deleted").catch(() => []),
      ]);
      setPeople(users);
      setProfiles(identities);
      setDisabled(off);
      setDeleted(gone);
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };
  useEffect(() => { load(); }, []);

  const addPerson = async () => {
    setBusy(true);
    setNote(null);
    try {
      await api.createUser({
        name: person.name.trim(),
        email: person.email.trim().toLowerCase(),
        password: person.password,
        role: person.role,
      });
      setPerson(BLANK_PERSON);
      await load();
      setNote({ text: `${person.name} can sign in now. Send them the password you just set.` });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const addProfile = async () => {
    setBusy(true);
    setNote(null);
    try {
      const made = await api.createProfile({
        name: profile.name.trim(),
        headline: profile.headline.trim(),
        platform: profile.platform.trim(),
        user_id: profile.user_id ? Number(profile.user_id) : null,
        dev_user_id: profile.dev_user_id ? Number(profile.dev_user_id) : null,
        email: profile.email.trim(),
        resume_url: profile.resume_url.trim(),
      });
      setProfile(BLANK_PROFILE);
      await load();
      setNote({ text: `${made.name} is ready. Whoever runs it can hand in a sheet for it.` });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const reassign = async (id, userId) => {
    try {
      await api.updateProfile(id, { user_id: Number(userId) });
      await load();
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  const setDeveloper = async (item, userId) => {
    try {
      await api.updateProfile(item.id, { dev_user_id: Number(userId) });
      await load();
      const dev = people.find((p) => p.id === Number(userId));
      setNote({
        text: dev
          ? `${dev.name} is now the developer behind ${item.name}. Interviews booked against `
            + `that profile land on their screen, and they can keep the resume and email current.`
          : `${item.name} has nobody behind it.`,
      });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  const setDashboard = async (item, open) => {
    try {
      await api.updateUser(item.id, { dashboard_visible: open });
      await load();
      setNote({
        text: open
          ? `${item.name} can now see their own dashboard.`
          : `${item.name}'s dashboard is closed. Their work is unaffected.`,
      });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  const setShared = async (id, share) => {
    try {
      await api.updateProfile(id, { share_progress: share });
      await load();
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  // Disable, delete and enable all end the same way, and none of them loses
  // anything — so they share one path and differ only in what they say.
  const act = async (run, said) => {
    setBusy(true);
    setNote(null);
    try {
      await run();
      await load();
      if (said) setNote({ text: said });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const disableProfile = (item) => {
    if (!window.confirm(
      `Disable ${item.name}? It comes off the working lists and keeps everything — ` +
      `so nothing it has already applied to will be offered to it again when you ` +
      `enable it.`)) return;
    act(() => api.disableProfile(item.id), `${item.name} is disabled.`);
  };

  const deleteProfile = (item) => {
    if (!window.confirm(
      `Delete ${item.name}? Every application, interview and assessment it left ` +
      `behind stays exactly as it is, and the reports still count them. It keeps ` +
      `its name too, so the work already recorded under it still adds up. You can ` +
      `enable it again from the deleted list.`)) return;
    act(() => api.deleteProfile(item.id),
        `${item.name} is deleted. Its records are untouched.`);
  };

  const enableProfile = (item) =>
    act(() => api.enableProfile(item.id),
        `${item.name} is back, with everything it had applied for.`);

  const disableUser = (item) => {
    if (!window.confirm(
      `Disable ${item.name}? They cannot sign in, but everything they did stays ` +
      `and so do the profiles they run. Enable puts them straight back to work.`)) return;
    act(() => api.disableUser(item.id), `${item.name} is disabled.`);
  };

  const enableUser = (item) =>
    act(() => api.enableUser(item.id), `${item.name} can sign in again.`);

  // Handing a seat over. The account keeps its id, so every profile it runs and
  // every figure recorded against it comes with the new name — which is the
  // point: reassigning profiles one by one would leave the work split between
  // somebody who has gone and somebody who has just arrived.
  const startEdit = (p) => {
    setNote(null);
    setEditing(p.id);
    setDraft({ name: p.name, email: p.email, role: p.role, password: "" });
  };

  const cancelEdit = () => { setEditing(null); setDraft(null); };

  const saveEdit = async (p) => {
    const body = { name: draft.name, email: draft.email, role: draft.role };
    if (draft.password) body.password = draft.password;
    if (draft.password && draft.password.length < 8) {
      setNote({ bad: true, text: "Use a password of at least 8 characters." });
      return;
    }
    const renamed = draft.name.trim() !== p.name;
    setBusy(true);
    setNote(null);
    try {
      await api.updateUser(p.id, body);
      cancelEdit();
      await load();
      setNote({
        text: renamed
          ? `${p.name} is now ${draft.name.trim()} — the same account, so every ` +
            `profile they ran came with it.`
          : `${draft.name.trim()} updated.`,
      });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const personReady = person.name && person.email && person.password.length >= 8;
  const profileReady = profile.name.trim() && profile.user_id;
  const bds = people.filter((p) => p.is_active);
  const devs = people.filter((p) => p.is_active && p.role === "dev");

  return (
    <div className="stack">
      <div>
        <h1>People and profiles</h1>
        <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
          A <b>person</b> signs in. A <b>profile</b> is the identity a job is
          applied under. One person can run several.
        </p>
        <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
            The <b>BD</b> runs the account and applies. The <b>developer</b> is who the
            client meets. Either may be left empty.
          </p>
      </div>

      {note && <div className={note.bad ? "notice" : "notice ok"}>{note.text}</div>}

      <section className="card pad">
        <h2>Add a profile</h2>
        <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
            Two profiles with the same skills are two candidates — both may go for
            one job. Only the same profile twice is blocked.
          </p>
        <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
            <b>On the board</b> decides whether a profile appears on the shared
            team board.
          </p>
        <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
            <b>Disable</b> takes a profile off the working lists for now.{" "}
            <b>Delete</b> takes it off for good. Neither loses anything — the
            applications, interviews and assessments stay exactly as they are, and
            both keep the profile&rsquo;s name so the work recorded under it still
            adds up.
          </p>
        <div className="row" style={{ marginTop: 12, flexWrap: "wrap" }}>
          <input placeholder="Profile name, e.g. Khuram" value={profile.name}
                 onChange={(e) => setProfile({ ...profile, name: e.target.value })} />
          <select value={profile.headline}
                  style={{ minWidth: 200 }}
                  onChange={(e) => setProfile({ ...profile, headline: e.target.value })}>
            <option value="">— select headline —</option>
            {HEADLINE_OPTIONS.filter(Boolean).map((label) => (
              <option key={label} value={label}>{label}</option>
            ))}
          </select>
          <select value={profile.platform} style={{ width: 170 }}
                  onChange={(e) => setProfile({ ...profile, platform: e.target.value })}>
            <option value="">— platform —</option>
            {PLATFORM_OPTIONS.filter(Boolean).map((label) => (
              <option key={label} value={label}>{label}</option>
            ))}
          </select>
          <input placeholder="Developer email (optional)" type="email" value={profile.email}
                 style={{ minWidth: 180 }}
                 onChange={(e) => setProfile({ ...profile, email: e.target.value })} />
          <input placeholder="Resume URL (optional)" value={profile.resume_url}
                 style={{ minWidth: 200 }}
                 onChange={(e) => setProfile({ ...profile, resume_url: e.target.value })} />
          <select value={profile.user_id}
                  onChange={(e) => setProfile({ ...profile, user_id: e.target.value })}>
            <option value="">— which BD runs it? —</option>
            {bds.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <select value={profile.dev_user_id}
                  onChange={(e) => setProfile({ ...profile, dev_user_id: e.target.value })}>
            <option value="">— which developer is it? —</option>
            {people.filter((p) => p.is_active).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}{p.role === "dev" ? "" : ` · ${ROLE_LABELS[p.role] || p.role}`}
              </option>
            ))}
          </select>
          <button onClick={addProfile} disabled={busy || !profileReady}>Add profile</button>
        </div>
      </section>

      <div className="card scroll">
        <table>
          <thead>
            <tr><th>Profile</th><th>Headline</th><th>Run by</th>
                <th title="The person the client would actually be meeting">Developer</th>
                <th title="What a BD attaches when applying under this profile">Resume</th>
                <th title="Whether this profile appears on the shared team board">On the board</th>
                <th /></tr>
          </thead>
          <tbody>
            {profiles.map((item) => (
              <tr key={item.id}>
                <td style={{ fontWeight: 500 }}>
                  {item.name}
                  {item.platform && (
                    <div className="muted" style={{ fontSize: 11 }}>{item.platform}</div>
                  )}
                </td>
                <td>{item.headline || <span className="muted">—</span>}</td>
                <td>
                  <select value={item.user_id || ""} onChange={(e) => reassign(item.id, e.target.value)}>
                    {!item.user_id && <option value="">— nobody —</option>}
                    {bds.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </td>
                <td>
                  <select value={item.dev_user_id || ""}
                          onChange={(e) => setDeveloper(item, e.target.value)}>
                    <option value="">— nobody —</option>
                    {people.filter((p) => p.is_active).map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}{p.role === "dev" ? "" : ` · ${ROLE_LABELS[p.role] || p.role}`}
                      </option>
                    ))}
                  </select>
                  {item.dev_user_id && (
                    <div style={{ marginTop: 4 }}><Availability value={item.availability} small /></div>
                  )}
                </td>
                <td>
                  {safeUrl(item.resume_url)
                    ? <a href={safeUrl(item.resume_url)} target="_blank" rel="noreferrer noopener">open</a>
                    : <span className="muted" title="The developer sets this on their own screen">
                        not set
                      </span>}
                </td>
                <td>
                  <label className="row" style={{ gap: 6 }}>
                    <input type="checkbox" checked={item.share_progress !== false}
                           onChange={(e) => setShared(item.id, e.target.checked)} />
                    {item.share_progress === false ? "hidden" : "shown"}
                  </label>
                </td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  <button className="link" disabled={busy}
                          onClick={() => disableProfile(item)}>Disable</button>
                  <button className="link" disabled={busy} style={{ marginLeft: 10 }}
                          onClick={() => deleteProfile(item)}>Delete</button>
                </td>
              </tr>
            ))}
            {!profiles.length && (
              <tr><td colSpan={7} className="muted">
                No profiles yet. Nobody can hand in a sheet until there is at least one.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      <OffList title="Disabled profiles" rows={disabled} busy={busy} onEnable={enableProfile}
               hint="Off the working lists for now, and still holding their names — which is
                     why a new profile cannot take one. Enable brings the profile back
                     exactly as it was, history and all." />

      <OffList title="Deleted profiles" rows={deleted} busy={busy} onEnable={enableProfile}
               hint="Off the lists for good, with everything they left behind intact: the
                     applications, interviews and assessments are all still there and the
                     reports still count them. They keep their names for that reason. Enable
                     puts one back if you deleted it by mistake." />

      <section className="card pad">
        <h2>Add a person</h2>
        <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
            A new BD starts with <b>no dashboard</b> — they can still log jobs and work
            their list. Turn it on when you want them measured.
          </p>
        <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
            The switch does not apply to a <b>developer</b>: their diary and resume are
            always theirs to see.
          </p>
        <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
            When somebody leaves and a new person takes their seat, <b>Edit</b> the
            account rather than making a second one: change the name, the email and
            the password, and every profile they ran comes with it. Making a new
            account instead leaves the work split between a name that has gone and a
            name that has just arrived.
          </p>
        <div className="row" style={{ marginTop: 12 }}>
          <input placeholder="Full name" value={person.name}
                 onChange={(e) => setPerson({ ...person, name: e.target.value })} />
          <input placeholder="Email" type="email" value={person.email} style={{ minWidth: 200 }}
                 onChange={(e) => setPerson({ ...person, email: e.target.value })} />
          <input placeholder="Password (8+ characters)" type="text" value={person.password}
                 onChange={(e) => setPerson({ ...person, password: e.target.value })} />
          <select value={person.role} onChange={(e) => setPerson({ ...person, role: e.target.value })}>
            <option value="bd">Business development</option>
            <option value="dev">Developer</option>
            <option value="admin">Manager</option>
          </select>
          <button onClick={addPerson} disabled={busy || !personReady}>Add</button>
        </div>
        {person.password && person.password.length < 8 && (
          <p className="muted" style={{ marginTop: 8, color: "var(--brick)" }}>
            Use at least 8 characters.
          </p>
        )}
      </section>

      <div className="card scroll">
        <table>
          <thead>
            <tr><th>Name</th><th>Email</th><th>Role</th><th>Profiles</th><th>Status</th>
                <th title="Whether this person may open their own dashboard of figures">Dashboard</th>
                <th /></tr>
          </thead>
          <tbody>
            {people.map((p) => {
              // A BD is measured on the profiles they run; a developer on the
              // ones they are sold under. Same column, two different questions.
              const theirs = p.role === "dev"
                ? profiles.filter((item) => item.dev_user_id === p.id)
                : profiles.filter((item) => item.user_id === p.id);
              return (
                <tr key={p.id} style={{ opacity: p.is_active ? 1 : 0.5 }}>
                  <td style={{ fontWeight: 500 }}>
                    {editing === p.id
                      ? <input value={draft.name} style={{ width: 150 }}
                               onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
                      : p.name}
                  </td>
                  <td className="mono" style={{ fontSize: 12 }}>
                    {editing === p.id
                      ? <input value={draft.email} type="email" style={{ width: 200 }}
                               onChange={(e) => setDraft({ ...draft, email: e.target.value })} />
                      : p.email}
                  </td>
                  <td className="muted">
                    {editing === p.id
                      ? <select value={draft.role}
                                onChange={(e) => setDraft({ ...draft, role: e.target.value })}>
                          <option value="bd">Business development</option>
                          <option value="dev">Developer</option>
                          <option value="admin">Manager</option>
                        </select>
                      : ROLE_LABELS[p.role] || p.role}
                  </td>
                  <td>
                    {theirs.length
                      ? <span className="row" style={{ gap: 5 }}>
                          {theirs.map((item) => <span className="pill on" key={item.id}>{item.name}</span>)}
                        </span>
                      : <span className="muted">
                          {p.role === "dev"
                            ? "not behind any profile — they see an empty desk"
                            : "none yet"}
                        </span>}
                  </td>
                  <td>
                    <span className={p.is_active ? "pill on" : "pill off"}>
                      {p.is_active ? "active" : "disabled"}
                    </span>
                  </td>
                  <td>
                    {p.role === "admin" ? (
                      <span className="muted">always</span>
                    ) : p.role === "dev" ? (
                      <span className="muted" title="A developer sees their own diary and resume, which is not a figure anybody has to decide to show them.">
                        not a figures screen
                      </span>
                    ) : (
                      <label className="row" style={{ gap: 6 }}>
                        <input type="checkbox" checked={!!p.dashboard_visible}
                               disabled={!p.is_active}
                               onChange={(e) => setDashboard(p, e.target.checked)} />
                        <span className={p.dashboard_visible ? "pill on" : "pill off"}>
                          {p.dashboard_visible ? "open" : "closed"}
                        </span>
                      </label>
                    )}
                  </td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    {editing === p.id ? (
                      <>
                        <input placeholder="New password (optional)" type="text"
                               value={draft.password} style={{ width: 170 }}
                               onChange={(e) => setDraft({ ...draft, password: e.target.value })} />
                        <button disabled={busy} style={{ marginLeft: 8 }}
                                onClick={() => saveEdit(p)}>Save</button>
                        <button className="link" style={{ marginLeft: 8 }}
                                onClick={cancelEdit}>Cancel</button>
                      </>
                    ) : (
                      <>
                        <button className="link" disabled={busy}
                                onClick={() => startEdit(p)}>Edit</button>
                        {p.is_active
                          ? <button className="link" disabled={busy} style={{ marginLeft: 10 }}
                                    onClick={() => disableUser(p)}>Disable</button>
                          : <button disabled={busy} style={{ marginLeft: 10 }}
                                    onClick={() => enableUser(p)}>Enable</button>}
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
