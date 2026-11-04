import { useEffect, useRef, useState, type CSSProperties, type PointerEvent as RPointerEvent, type ReactNode, type Ref, type SyntheticEvent } from "react";

export type ViewMode = "edited" | "original" | "split" | "side";
interface Props { originalUrl: string; editedUrl: string | null; rendering: boolean; mode: ViewMode }
interface Zoom { s: number; x: number; y: number }

const MAX_ZOOM = 6;
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

export default function ComparisonViewer({ originalUrl, editedUrl, rendering, mode }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 640, h: 520 });
  const [dims, setDims] = useState<{ w: number; h: number } | null>(null);
  const [z, setZ] = useState<Zoom>({ s: 1, x: 0, y: 0 });
  const [split, setSplit] = useState(50);
  const pan = useRef<{ px: number; py: number; x: number; y: number } | null>(null);
  const splitBox = useRef<HTMLDivElement>(null);

  useEffect(() => { setDims(null); setZ({ s: 1, x: 0, y: 0 }); }, [originalUrl]);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  const sideBySide = mode === "side" && editedUrl !== null;
  const panes = sideBySide ? 2 : 1;
  const availW = size.w / panes - (panes === 2 ? 4 : 0);
  const fit = dims ? Math.min(availW / dims.w, size.h / dims.h) : 1;
  const bw = dims ? dims.w * fit : availW;
  const bh = dims ? dims.h * fit : size.h;

  function limit(s: number, x: number, y: number): Zoom {
    if (s <= 1.001) return { s: 1, x: 0, y: 0 };
    return { s, x: clamp(x, -(bw * s) / 2, (bw * s) / 2), y: clamp(y, -(bh * s) / 2, (bh * s) / 2) };
  }
  function zoomAt(factor: number, px = 0, py = 0) {
    setZ((c) => {
      const ns = clamp(c.s * factor, 1, MAX_ZOOM);
      const k = ns / c.s;
      return limit(ns, px - (px - c.x) * k, py - (py - c.y) * k);
    });
  }

  // Wheel zoom needs a non-passive listener so the page does not scroll while zooming.
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      const pane = (e.target as HTMLElement).closest("[data-pane]") as HTMLElement | null;
      if (!pane) return;
      e.preventDefault();
      const r = pane.getBoundingClientRect();
      zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left - r.width / 2, e.clientY - r.top - r.height / 2);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);  // eslint-disable-next-line
  });

  function startPan(e: RPointerEvent) {
    if (z.s <= 1) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    pan.current = { px: e.clientX, py: e.clientY, x: z.x, y: z.y };
  }
  function movePan(e: RPointerEvent) {
    const p = pan.current;
    if (p) setZ((c) => limit(c.s, p.x + e.clientX - p.px, p.y + e.clientY - p.py));
  }

  function moveSplit(e: RPointerEvent) {
    if (!(e.buttons & 1) && e.pointerType === "mouse") return;
    const r = splitBox.current?.getBoundingClientRect();
    if (r) setSplit(clamp(((e.clientX - r.left) / r.width) * 100, 0, 100));
  }

  const onLoadDims = (e: SyntheticEvent<HTMLImageElement>) => {
    const i = e.currentTarget;
    if (i.naturalWidth) setDims({ w: i.naturalWidth, h: i.naturalHeight });
  };

  const showEdited = editedUrl !== null;
  const label = (t: string, side: "l" | "r") => (
    <span className={`pointer-events-none absolute top-3 ${side === "l" ? "left-3" : "right-3"} rounded-md bg-ink/80 px-2 py-1 text-xs font-semibold tracking-wider`}>{t}</span>
  );

  function pane(content: ReactNode, labels: ReactNode, ref?: Ref<HTMLDivElement>) {
    return (
      <div data-pane className="relative overflow-hidden rounded-xl bg-panel"
        style={{ width: availW, height: size.h, cursor: z.s > 1 ? "grab" : "default", touchAction: z.s > 1 ? "none" : "pan-y" }}
        onPointerDown={startPan} onPointerMove={movePan} onPointerUp={() => (pan.current = null)} onPointerCancel={() => (pan.current = null)}>
        <div ref={ref} style={{ position: "absolute", left: "50%", top: "50%", width: bw, height: bh, marginLeft: -bw / 2, marginTop: -bh / 2,
          transform: `translate(${z.x}px, ${z.y}px) scale(${z.s})` }}>
          {content}
        </div>
        {labels}
      </div>
    );
  }
  const img = (src: string, alt: string, extra?: CSSProperties, load = false) => (
    <img src={src} alt={alt} draggable={false} onLoad={load ? onLoadDims : undefined}
      className="absolute inset-0 h-full w-full select-none" style={extra} />
  );

  let body: ReactNode;
  if (mode === "split" && showEdited) {
    const inv = 1 / z.s;
    body = pane(
      <>
        {img(originalUrl, "Original photo", undefined, true)}
        {img(editedUrl!, "Edited photo", { clipPath: `inset(0 0 0 ${split}%)` })}
        <div role="slider" tabIndex={0} aria-label="Before and after divider" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(split)}
          className="absolute top-0 bottom-0 cursor-ew-resize outline-none" style={{ left: `${split}%`, width: 36 * inv, marginLeft: -18 * inv, touchAction: "none" }}
          onPointerDown={(e) => { e.stopPropagation(); e.currentTarget.setPointerCapture(e.pointerId); moveSplit(e); }}
          onPointerMove={(e) => { e.stopPropagation(); moveSplit(e); }}
          onKeyDown={(e) => { if (e.key === "ArrowLeft") setSplit((v) => clamp(v - 2, 0, 100)); if (e.key === "ArrowRight") setSplit((v) => clamp(v + 2, 0, 100)); }}>
          <div className="absolute left-1/2 top-0 h-full -translate-x-1/2 bg-white shadow" style={{ width: 2 * inv }} />
          <div className="absolute left-1/2 top-1/2 flex -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white text-ink shadow-lg"
            style={{ width: 34 * inv, height: 34 * inv, fontSize: 14 * inv }} aria-hidden>↔</div>
        </div>
      </>,
      <>{label("BEFORE", "l")}{label("AFTER", "r")}</>,
      splitBox,
    );
  } else if (sideBySide) {
    body = (
      <div className="flex h-full w-full items-center justify-center gap-1">
        {pane(img(originalUrl, "Original photo", undefined, true), label("BEFORE", "l"))}
        {pane(img(editedUrl!, "Edited photo"), label("AFTER", "l"))}
      </div>
    );
  } else {
    const useEdited = mode === "edited" && showEdited;
    body = pane(img(useEdited ? editedUrl! : originalUrl, useEdited ? "Edited photo" : "Original photo", undefined, true), label(useEdited ? "AFTER" : "BEFORE", "l"));
  }

  const zoomBtn = "h-8 w-8 rounded-lg bg-ink/80 text-lg leading-none hover:bg-ink focus-visible:outline";
  return (
    <div>
      <div ref={wrap} className="relative flex h-[64vh] min-h-[320px] w-full items-center justify-center">
        {body}
        {rendering && <span role="status" className="pointer-events-none absolute left-1/2 top-3 -translate-x-1/2 rounded-md bg-ink/80 px-2 py-1 text-xs text-gold">Rendering…</span>}
        <div className="absolute bottom-3 right-3 flex items-center gap-1">
          <button className={zoomBtn} aria-label="Zoom out" onClick={() => zoomAt(1 / 1.3)}>−</button>
          <button className="h-8 rounded-lg bg-ink/80 px-2 text-xs tabular-nums hover:bg-ink" aria-label="Fit to screen" onClick={() => setZ({ s: 1, x: 0, y: 0 })}>{Math.round(z.s * 100)}%</button>
          <button className={zoomBtn} aria-label="Zoom in" onClick={() => zoomAt(1.3)}>+</button>
        </div>
      </div>
    </div>
  );
}
