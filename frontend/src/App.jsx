import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api, getToken, setToken } from "./api.js";
import Login from "./views/Login.jsx";
import BdHome from "./views/BdHome.jsx";
import AdminHome from "./views/AdminHome.jsx";
import Dashboard from "./views/Dashboard.jsx";
import DevHome from "./views/DevHome.jsx";
import DevProfiles from "./views/DevProfiles.jsx";
import ManagerDashboard from "./views/ManagerDashboard.jsx";
import People from "./views/People.jsx";
import { Loading } from "./views/widgets.jsx";
import { CommandPalette, ThemeToggle, ToastHost } from "./views/shell.jsx";

/** The shell: who is signed in, which screen they are on, and the things that
 *  sit above every screen — toasts, the command palette, the theme.
 *
 * `pane` is a sub-tab inside a screen, lifted up here so the palette can jump
 * straight to one. Without it ⌘K could only reach the two or three top-level
 * views, which is the smaller half of where anybody actually goes.
 */

const TABS = {
  admin: [
    { view: "dashboard", label: "Overview" },
    { view: "work", label: "Cycles" },
    { view: "people", label: "People" },
  ],
  // A BD whose manager has not opened their dashboard lands on their work
  // instead, and never sees a tab for a screen the server would refuse.
  bd: [
    { view: "dashboard", label: "Dashboard", needs: "dashboard" },
    { view: "work", label: "My work" },
  ],
  // A developer always has their desk: it is a calendar, not a set of figures
  // somebody has to decide to show them.
  dev: [
    { view: "dashboard", label: "My desk" },
    { view: "details", label: "My details" },
  ],
};

/* The sub-tabs worth reaching directly — the ones otherwise two clicks and a
   scroll away. */
const PANES = {
  bd: [
    { label: "Jobs I applied to", view: "work", pane: "applied" },
    { label: "New jobs", view: "work", pane: "new" },
    { label: "All jobs", view: "work", pane: "record" },
    { label: "Interviews", view: "work", pane: "interviews" },
    { label: "Assessments", view: "work", pane: "assessments" },
  ],
  dev: [
    { label: "Today", view: "dashboard", pane: "desk" },
    { label: "Every interview", view: "dashboard", pane: "diary" },
    { label: "Assessments", view: "dashboard", pane: "assessments" },
  ],
  admin: [],
};

export default function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState("dashboard");
  // Set when the palette jumps to a sub-tab; cleared by the screen once it has
  // been honoured, so choosing the same entry twice works.
  const [pane, setPane] = useState(null);
  const [booting, setBooting] = useState(true);

  const signOut = useCallback(() => {
    setToken("");
    setUser(null);
    setView("dashboard");
  }, []);

  useEffect(() => {
    window.addEventListener("dispatch:signed-out", signOut);
    return () => window.removeEventListener("dispatch:signed-out", signOut);
  }, [signOut]);

  useEffect(() => {
    if (!getToken()) {
      setBooting(false);
      return;
    }
    api.me()
      .then((me) => {
        setUser(me);
        if (me.role === "bd" && !me.dashboard_visible) setView("work");
      })
      .catch(() => setToken(""))
      .finally(() => setBooting(false));
  }, []);

  const go = useCallback((nextView, nextPane = null) => {
    setView(nextView);
    setPane(nextPane);
  }, []);

  const role = user?.role;
  const tabs = useMemo(
    () => (TABS[role] || []).filter(
      (t) => t.needs !== "dashboard" || user?.dashboard_visible
    ),
    [role, user?.dashboard_visible]
  );

  const commands = useMemo(() => {
    if (!user) return [];
    const where = { admin: "Manager", bd: "BD", dev: "Developer" }[role];
    return [
      ...tabs.map((t) => ({ label: t.label, where, run: () => go(t.view) })),
      ...(PANES[role] || []).map((p) => ({
        label: p.label, where, run: () => go(p.view, p.pane),
      })),
      { label: "Sign out", where: "Session", run: signOut },
    ];
  }, [user, role, tabs, go, signOut]);

  if (booting) return <div className="wrap"><Loading lines={2} /></div>;

  if (!user) {
    return (
      <ToastHost>
        <Login onSignedIn={(me) => {
          setUser(me);
          setView(me.role === "bd" && !me.dashboard_visible ? "work" : "dashboard");
        }} />
      </ToastHost>
    );
  }

  const isAdmin = role === "admin";
  const isDev = role === "dev";
  const seen = () => setPane(null);

  return (
    <ToastHost>
      <header className="top">
        <span className="brand">Dispatch</span>

        <nav className="tabs" aria-label="Sections">
          {tabs.map((t) => (
            <button key={t.view} className="tab" aria-current={view === t.view}
                    onClick={() => go(t.view)}>
              {t.label}
            </button>
          ))}
        </nav>

        <span className="spacer" />
        <span className="hint" style={{ whiteSpace: "nowrap" }}>{user.name}</span>
        <ThemeToggle />
        <button className="link" onClick={signOut}>Sign out</button>
      </header>

      <CommandPalette commands={commands} />

      {/* Keyed on the view so switching replays the entrance rather than
          swapping the contents of a container that never moved. One animation
          for the whole screen — never one per row. */}
      <main className="wrap enter" key={view}>
        {isAdmin ? (
          view === "people" ? <People />
            : view === "work" ? <AdminHome />
              : <ManagerDashboard onOpenBatches={() => go("work")} />
        ) : isDev ? (
          view === "details"
            ? <DevProfiles />
            : <DevHome onOpenProfiles={() => go("details")} pane={pane} onPaneSeen={seen} />
        ) : (
          view === "dashboard" && user.dashboard_visible
            ? <Dashboard onOpenWork={() => go("work")} />
            : <BdHome pane={pane} onPaneSeen={seen} />
        )}
      </main>
    </ToastHost>
  );
}
