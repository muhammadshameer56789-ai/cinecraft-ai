import { useCallback, useReducer } from "react";
import { canUndo, reducer, type A, type H } from "./historyReducer";

export function useEditHistory<T>(initial: T) {
  const [s, dispatch] = useReducer(reducer as (s: H<T>, a: A<T>) => H<T>, { past: [], present: initial, future: [], pending: null });
  return {
    state: s.present,
    canUndo: canUndo(s),
    canRedo: s.future.length > 0,
    apply: useCallback((value: T) => dispatch({ type: "apply", value }), []),
    transient: useCallback((value: T) => dispatch({ type: "transient", value }), []),
    commit: useCallback(() => dispatch({ type: "commit" }), []),
    undo: useCallback(() => dispatch({ type: "undo" }), []),
    redo: useCallback(() => dispatch({ type: "redo" }), []),
    reset: useCallback((value: T) => dispatch({ type: "reset", value }), []),
  };
}
