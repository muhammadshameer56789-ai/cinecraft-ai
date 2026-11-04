import { ADJUSTMENTS, type AdjKey, type Adjustments, hasAdjustments } from "../adjustments";

interface Props {
  values: Adjustments;
  onChange: (key: AdjKey, value: number) => void;  // live, while dragging
  onCommit: () => void;                            // drag finished: one undo step
  onReset: (key?: AdjKey) => void;
}

export default function AdjustPanel({ values, onChange, onCommit, onReset }: Props) {
  return (
    <section aria-label="Manual adjustments">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Adjust</h2>
        <button onClick={() => onReset()} disabled={!hasAdjustments(values)}
          className="rounded-lg border border-edge px-2.5 py-1 text-sm hover:border-dim disabled:opacity-40">Reset all</button>
      </div>
      <p className="mb-3 text-xs text-dim">Adjustments sit on top of the chosen style and are not scaled by Intensity. Switching style keeps them.</p>
      <div className="space-y-3">
        {ADJUSTMENTS.map((a) => (
          <div key={a.key}>
            <div className="flex items-center justify-between text-sm">
              <label htmlFor={`adj-${a.key}`} onDoubleClick={() => onReset(a.key)} title="Double-click to reset" className="cursor-default">{a.label}</label>
              <output className={`tabular-nums ${values[a.key] ? "text-gold" : "text-dim"}`}>{values[a.key]}</output>
            </div>
            <input id={`adj-${a.key}`} type="range" min={a.min} max={a.max} value={values[a.key]} className="w-full accent-[#d9a441]"
              onChange={(e) => onChange(a.key, +e.target.value)} onPointerUp={onCommit} onKeyUp={onCommit} onBlur={onCommit} />
          </div>
        ))}
      </div>
    </section>
  );
}
