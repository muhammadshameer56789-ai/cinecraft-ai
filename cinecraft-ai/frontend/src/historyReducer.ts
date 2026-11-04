/** Predictable history: a drag on a slider is ONE undo step (transient updates, then commit). */
export interface H<T> { past: T[]; present: T; future: T[]; pending: T | null }
export type A<T> =
  | { type: "transient"; value: T } | { type: "commit" } | { type: "apply"; value: T }
  | { type: "undo" } | { type: "redo" } | { type: "reset"; value: T };

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const LIMIT = 100;

export function commit<T>(s: H<T>): H<T> {
  if (s.pending === null) return s;
  if (same(s.pending, s.present)) return { ...s, pending: null };
  return { ...s, past: [...s.past, s.pending].slice(-LIMIT), future: [], pending: null };
}

export function reducer<T>(s: H<T>, a: A<T>): H<T> {
  switch (a.type) {
    case "transient": return { ...s, pending: s.pending ?? s.present, present: a.value };
    case "commit": return commit(s);
    case "apply": {
      const c = commit(s);
      if (same(c.present, a.value)) return c;
      return { past: [...c.past, c.present].slice(-LIMIT), present: a.value, future: [], pending: null };
    }
    case "undo": {
      const c = commit(s);
      if (!c.past.length) return c;
      return { past: c.past.slice(0, -1), present: c.past[c.past.length - 1], future: [c.present, ...c.future], pending: null };
    }
    case "redo": {
      const c = commit(s);
      if (!c.future.length) return c;
      return { past: [...c.past, c.present], present: c.future[0], future: c.future.slice(1), pending: null };
    }
    case "reset": return { past: [], present: a.value, future: [], pending: null };
  }
}

export const canUndo = <T,>(s: H<T>) => s.past.length > 0 || (s.pending !== null && !same(s.pending, s.present));
