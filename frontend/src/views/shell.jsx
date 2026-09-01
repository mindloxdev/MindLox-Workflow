import React, {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from "react";

/** The parts of the app that are not a screen: toasts, the command palette,
 *  and the theme.
 *
 * All three are shell rather than page. They outlive whatever view is mounted,
 * they are reachable from anywhere, and none of them belongs to a particular
 * role — so they live here instead of being threaded through every screen.
 */

/* ═══ Toasts ══════════════════════════════════════════════════════════════
 *
 * Transient feedback moves out of the page and into a corner.
 *
 * The old inline notice had one flaw that cost people work: it appeared at the
 * top of a long screen, so a confirmation for something done at the bottom was
 * printed somewhere the person was not looking. A toast is in the same place
 * every time, whatever the scroll position.
 *
 * Warnings that are still true tomorrow — an overdue take-home, a cleared
 * round with nothing after it — stay as inline notices on purpose. Those are
 * state, not events, and state that dismisses itself after four seconds is
 * state nobody acts on.
 */

const ToastContext = createContext(() => {});

export function useToast() {
  return useContext(ToastContext);
}

let nextId = 1;

export function ToastHost({ children }) {
  const [items, setItems] = useState([]);
  const timers = useRef(new Map());

  const dismiss = useCallback((id) => {
    // Marked leaving first so the exit animation runs, then removed. Dropping
    // the node straight out of the DOM is what makes a toast look like a bug.
    setItems((all) => all.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    setTimeout(() => setItems((all) => all.filter((t) => t.id !== id)), 200);
  }, []);

  const push = useCallback((text, tone = "ok") => {
    if (!text) return;
    const id = nextId++;
    setItems((all) => [...all.slice(-2), { id, text, tone }]);
    // An error stays until it is read; a confirmation does not need to.
    const life = tone === "bad" ? 7000 : 4000;
    timers.current.set(id, setTimeout(() => dismiss(id), life));
  }, [dismiss]);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach(clearTimeout);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.tone}${t.leaving ? " leaving" : ""}`}>
            <span>{t.text}</span>
            <button className="link" onClick={() => dismiss(t.id)} aria-label="Dismiss">
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/* ═══ Command palette ═════════════════════════════════════════════════════
 *
 * ⌘K / Ctrl-K, and every destination in the app is two keystrokes away.
 *
 * This app hides a lot behind sub-tabs: a BD's interviews are two clicks and a
 * scroll from the dashboard, their assessments another. That is fine the first
 * week and tiresome the tenth. The palette flattens all of it — the tabs *and*
 * the sub-tabs — into one list you can type at.
 *
 * Matching is subsequence rather than substring, so "jr" finds "Job record"
 * the way it does in an editor. Filtering happens on a list of a dozen items,
 * so there is nothing to memoise and no reason to debounce.
 */

function matches(query, label) {
  const q = query.toLowerCase().replace(/\s+/g, "");
  if (!q) return true;
  const text = label.toLowerCase();
  let at = 0;
  for (const ch of q) {
    at = text.indexOf(ch, at);
    if (at === -1) return false;
    at += 1;
  }
  return true;
}

export function CommandPalette({ commands }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const field = useRef(null);

  const found = useMemo(
    () => commands.filter((c) => matches(query, `${c.label} ${c.where || ""}`)),
    [commands, query]
  );

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((on) => !on);
        setQuery("");
        setCursor(0);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) field.current?.focus();
  }, [open]);

  useEffect(() => { setCursor(0); }, [query]);

  if (!open) return null;

  const run = (command) => {
    setOpen(false);
    command.run();
  };

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((n) => Math.min(n + 1, found.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((n) => Math.max(n - 1, 0));
    } else if (e.key === "Enter" && found[cursor]) {
      e.preventDefault();
      run(found[cursor]);
    }
  };

  return (
    <div className="scrim" onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette">
        <input ref={field} value={query} placeholder="Go to…"
               onChange={(e) => setQuery(e.target.value)} onKeyDown={onKeyDown} />
        {found.length === 0 ? (
          <div className="palette-empty">Nothing matches “{query}”.</div>
        ) : (
          <div className="palette-list">
            {found.map((c, i) => (
              <button key={c.label + (c.where || "")} className="palette-item"
                      data-active={i === cursor}
                      onMouseEnter={() => setCursor(i)}
                      onClick={() => run(c)}>
                {c.label}
                {c.where && <span className="where">{c.where}</span>}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** The hint that the palette exists. Nobody presses ⌘K on an app that has
 *  never mentioned it. */
export function CommandHint({ onOpen }) {
  const mac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || "");
  return (
    <button className="theme-toggle" onClick={onOpen} title="Search and jump anywhere">
      <span className="kbd" style={{ border: "none", background: "none", padding: 0 }}>
        {mac ? "⌘" : "Ctrl "}K
      </span>
    </button>
  );
}

/** Light, dark, or whatever the machine is set to.
 *
 * Three states, and the third is the default. "Follow the system" is the only
 * setting still right at six in the evening, and an app that forces a choice
 * at first load has taken one away.
 *
 * The first paint is settled in index.html, before React exists — this only
 * changes it afterwards and remembers the change.
 */
export function ThemeToggle() {
  const [mode, setMode] = useState(() => {
    try {
      return localStorage.getItem("dispatch.theme") || "system";
    } catch {
      return "system";                        // private window, or storage blocked
    }
  });

  useEffect(() => {
    const root = document.documentElement;
    if (mode === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", mode);
    try {
      if (mode === "system") localStorage.removeItem("dispatch.theme");
      else localStorage.setItem("dispatch.theme", mode);
    } catch {
      /* the theme still applies for this session */
    }
  }, [mode]);

  const next = { system: "light", light: "dark", dark: "system" };
  const glyph = { system: "◐", light: "☀", dark: "☾" };

  return (
    <button className="theme-toggle" onClick={() => setMode(next[mode])}
            title={`Theme: ${mode}. Click for ${next[mode]}.`}
            aria-label={`Theme: ${mode}`}>
      {glyph[mode]}
    </button>
  );
}
