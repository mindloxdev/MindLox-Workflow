import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { Availability, CopyButton, Skills } from "./widgets.jsx";

/** What a client is handed when the team applies as you.
 *
 * The developer edits these, not the manager. Which resume goes out, which
 * address a client replies to, whether you can start next week — routing every
 * correction to that through somebody else is how it ends up out of date, and
 * an out-of-date resume link is worse than no link at all.
 *
 * The identity itself — its name, who runs it, whether it is on the team board
 * — stays the manager's, and the server refuses a change to any of it. Those
 * decide what other people see.
 */

const FIELDS = [
  { key: "email", label: "Email on the resume", placeholder: "you@example.com",
    hint: "Where a client replies. It does not have to be your sign-in address." },
  { key: "resume_url", label: "Resume link", placeholder: "https://…",
    hint: "A link your BD can paste into an application. Must start with http:// or https://." },
  { key: "skills", label: "Skills", placeholder: "Python, RAG, LangChain, AWS",
    hint: "Comma separated. Your BD reads these when deciding what to apply for." },
  { key: "rate", label: "Rate", placeholder: "$45–60/hr",
    hint: "However you want it said. Nobody does arithmetic on it." },
  { key: "timezone", label: "Working hours", placeholder: "PKT · 2pm–10pm ET overlap",
    hint: "When a client can actually reach you. Interview times are always Eastern." },
];

export default function DevProfiles() {
  const [profiles, setProfiles] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [note, setNote] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = async () => {
    try {
      const rows = await api.listProfiles();
      setProfiles(rows);
      setDrafts(Object.fromEntries(rows.map((p) => [p.id, {
        email: p.email || "", resume_url: p.resume_url || "", skills: p.skills || "",
        rate: p.rate || "", timezone: p.timezone || "", bio: p.bio || "",
        availability: p.availability || "open",
      }])));
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };
  useEffect(() => { load(); }, []);

  const save = async (profile) => {
    setBusy(profile.id);
    setNote(null);
    try {
      await api.updateProfile(profile.id, drafts[profile.id]);
      await load();
      setNote({ text: `Saved. That is what goes out the next time your team applies as ${profile.name}.` });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(null);
    }
  };

  // Availability is worth saving the moment it changes — it is the one field a
  // colleague acts on within the hour, and a draft nobody pressed Save on is a
  // developer who is quietly still shown as free.
  const setAvailability = async (profile, value) => {
    setDrafts((all) => ({ ...all, [profile.id]: { ...all[profile.id], availability: value } }));
    try {
      await api.updateProfile(profile.id, { availability: value });
      await load();
      setNote({
        text: value === "booked"
          ? `${profile.name} is marked booked up. Your team can see it before they apply.`
          : `${profile.name} is marked ${value === "open" ? "as taking work" : "limited"}.`,
      });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  const dirty = (p) => {
    const draft = drafts[p.id] || {};
    return FIELDS.some((f) => (draft[f.key] || "") !== (p[f.key] || ""))
      || (draft.bio || "") !== (p.bio || "");
  };

  if (!profiles.length) {
    return (
      <div className="stack">
        <h1>Your details</h1>
        <div className="notice">
          No profile is attached to you yet. A profile is the identity your team applies
          under — your name and resume as the client sees them. Ask your manager to put you
          behind one under <b>People and profiles</b>.
        </div>
      </div>
    );
  }

  return (
    <div className="stack">
      <div>
        <h1>Your details</h1>
        <p className="hint" style={{ marginTop: 3, maxWidth: 640 }}>
          One card per identity you are sold under. This is what a client is
          handed, so it is yours to keep right.
        </p>
      </div>

      {note && <div className={note.bad ? "notice" : "notice ok"}>{note.text}</div>}

      {profiles.map((profile) => {
        const draft = drafts[profile.id] || {};
        const set = (key, value) =>
          setDrafts((all) => ({ ...all, [profile.id]: { ...all[profile.id], [key]: value } }));

        return (
          <section className="card pad stack" key={profile.id} style={{ gap: 14 }}>
            <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <h2>{profile.name}</h2>
                <p className="muted" style={{ marginTop: 3 }}>
                  {profile.headline || "no headline"}
                  {profile.platform ? ` · ${profile.platform}` : ""}
                  {profile.owner ? ` · applied by ${profile.owner}` : " · nobody is running this yet"}
                </p>
              </div>
              <Availability value={profile.availability} />
            </div>

            <div>
              <label htmlFor={`av-${profile.id}`}>Can you take work?</label>
              <div className="row" style={{ marginTop: 6, gap: 8 }}>
                {[["open", "Taking work"], ["limited", "Limited"], ["booked", "Booked up"]].map(
                  ([value, label]) => (
                    <button key={value}
                            className={draft.availability === value ? "" : "ghost"}
                            onClick={() => setAvailability(profile, value)}>
                      {label}
                    </button>
                  )
                )}
              </div>
              <p className="hint">
            Saved on press. Everything else waits for <b>Save</b>.
          </p>
            </div>

            <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))" }}>
              {FIELDS.map((field) => (
                <div key={field.key}>
                  <label htmlFor={`${field.key}-${profile.id}`}>{field.label}</label>
                  <input id={`${field.key}-${profile.id}`} style={{ width: "100%", marginTop: 4 }}
                         placeholder={field.placeholder} value={draft[field.key] || ""}
                         onChange={(e) => set(field.key, e.target.value)} />
                  <p className="muted" style={{ marginTop: 4, fontSize: 11.5 }}>{field.hint}</p>
                </div>
              ))}
            </div>

            <div>
              <label htmlFor={`bio-${profile.id}`}>How your BD should pitch you</label>
              <input id={`bio-${profile.id}`} style={{ width: "100%", marginTop: 4 }}
                     placeholder="Six years on production ML. Shipped two RAG systems on AWS."
                     value={draft.bio || ""} onChange={(e) => set("bio", e.target.value)} />
              <p className="muted" style={{ marginTop: 4, fontSize: 11.5 }}>
                One or two lines. They are writing a cover note at speed; give them something
                true to write.
              </p>
            </div>

            {profile.skills && (
              <div className="row" style={{ gap: 8 }}>
                <span className="muted">reads as</span>
                <Skills value={draft.skills} />
              </div>
            )}

            <div className="row" style={{ justifyContent: "space-between" }}>
              <div className="row" style={{ gap: 10 }}>
                <button onClick={() => save(profile)} disabled={busy === profile.id || !dirty(profile)}>
                  {busy === profile.id ? "Saving…" : dirty(profile) ? "Save" : "Saved"}
                </button>
                {dirty(profile) && (
                  <button className="link" onClick={() => setDrafts((all) => ({
                    ...all,
                    [profile.id]: {
                      email: profile.email || "", resume_url: profile.resume_url || "",
                      skills: profile.skills || "", rate: profile.rate || "",
                      timezone: profile.timezone || "", bio: profile.bio || "",
                      availability: profile.availability || "open",
                    },
                  }))}>Undo</button>
                )}
              </div>
              <div className="row" style={{ gap: 8 }}>
                {/^https?:\/\//i.test(profile.resume_url) && (
                  <>
                    <a href={profile.resume_url} target="_blank" rel="noreferrer noopener">
                      open the resume
                    </a>
                    <CopyButton value={profile.resume_url} label="copy link" />
                  </>
                )}
              </div>
            </div>

            {!profile.resume_url && (
              <div className="notice">
                  <b>No resume link.</b> Your BD is applying with nothing to attach.
                </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
