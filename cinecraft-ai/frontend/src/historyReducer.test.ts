import assert from "node:assert/strict";
import { test } from "node:test";
import { canUndo, reducer, type H } from "./historyReducer";

const init = (v: number): H<number> => ({ past: [], present: v, future: [], pending: null });
const run = (s: H<number>, ...acts: Parameters<typeof reducer<number>>[1][]) => acts.reduce((x, a) => reducer(x, a), s);

test("a slider drag is one undo step", () => {
  let s = run(init(0), { type: "transient", value: 1 }, { type: "transient", value: 2 }, { type: "transient", value: 3 }, { type: "commit" });
  assert.equal(s.present, 3); assert.deepEqual(s.past, [0]);
  s = run(s, { type: "undo" });
  assert.equal(s.present, 0);
});

test("undo while still dragging commits first, then steps back", () => {
  const s = run(init(0), { type: "transient", value: 5 }, { type: "undo" });
  assert.equal(s.present, 0); assert.deepEqual(s.future, [5]);
});

test("redo restores, and a new edit clears the redo stack", () => {
  let s = run(init(0), { type: "apply", value: 1 }, { type: "apply", value: 2 }, { type: "undo" }, { type: "undo" });
  assert.equal(s.present, 0); assert.equal(s.future.length, 2);
  s = run(s, { type: "redo" }); assert.equal(s.present, 1);
  s = run(s, { type: "apply", value: 9 }); assert.equal(s.future.length, 0); assert.equal(s.present, 9);
});

test("no-op edits do not create history", () => {
  const s = run(init(4), { type: "apply", value: 4 }, { type: "transient", value: 7 }, { type: "transient", value: 4 }, { type: "commit" });
  assert.equal(s.past.length, 0); assert.equal(canUndo(s), false);
});

test("canUndo is true while a drag is pending", () => {
  assert.equal(canUndo(run(init(0), { type: "transient", value: 3 })), true);
});

test("undo/redo at the ends do nothing; reset clears everything", () => {
  assert.equal(run(init(1), { type: "undo" }).present, 1);
  assert.equal(run(init(1), { type: "redo" }).present, 1);
  const s = run(init(0), { type: "apply", value: 1 }, { type: "reset", value: 0 });
  assert.equal(s.past.length + s.future.length, 0);
});

test("history is capped", () => {
  let s = init(0);
  for (let i = 1; i <= 150; i++) s = reducer(s, { type: "apply", value: i });
  assert.equal(s.past.length, 100);
});
