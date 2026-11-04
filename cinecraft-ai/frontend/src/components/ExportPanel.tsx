import { useState } from "react";
import { exportImage, type ExportOptions } from "../api";
import type { EditState } from "../adjustments";

interface Props { imageId: string; edit: EditState; width: number; height: number }
const FORMATS: ExportOptions["format"][] = ["jpeg", "png", "webp"];

export default function ExportPanel({ imageId, edit, width, height }: Props) {
  const [format, setFormat] = useState<ExportOptions["format"]>("jpeg");
  const [quality, setQuality] = useState(92);
  const [maxSide, setMaxSide] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const long = Math.max(width, height);
  const sizes = [3840, 2048, 1080].filter((s) => s < long);

  async function run() {
    setBusy(true); setErr(null); setMsg(null);
    try {
      const out = await exportImage(imageId, edit, { format, quality, max_side: maxSide });
      const url = URL.createObjectURL(out.blob);
      const a = document.createElement("a");
      a.href = url; a.download = out.filename; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
      setMsg(`Saved ${out.filename} · ${out.width} × ${out.height} · ${(out.blob.size / 1048576).toFixed(2)} MB${out.notes ? ` · ${out.notes}` : ""}`);
    } catch (e) { setErr(e instanceof Error ? e.message : "Export failed."); }
    finally { setBusy(false); }
  }

  const seg = (on: boolean) => `rounded-lg border px-3 py-1.5 text-sm ${on ? "border-gold text-gold" : "border-edge hover:border-dim"}`;
  return (
    <section className="rounded-2xl bg-panel p-5" aria-label="Export">
      <h2 className="text-lg font-semibold">Export</h2>
      <div className="mt-3 flex gap-2" role="group" aria-label="Format">
        {FORMATS.map((f) => <button key={f} className={seg(format === f)} aria-pressed={format === f} onClick={() => setFormat(f)}>{f === "jpeg" ? "JPEG" : f.toUpperCase()}</button>)}
      </div>
      {format !== "png" && (
        <div className="mt-4">
          <div className="flex justify-between text-sm"><label htmlFor="q">Quality</label><output className="tabular-nums text-gold">{quality}</output></div>
          <input id="q" type="range" min={50} max={100} value={quality} onChange={(e) => setQuality(+e.target.value)} className="w-full accent-[#d9a441]" />
        </div>
      )}
      <div className="mt-4">
        <label htmlFor="size" className="text-sm">Size</label>
        <select id="size" value={maxSide ?? ""} onChange={(e) => setMaxSide(e.target.value ? +e.target.value : null)}
          className="mt-1 w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm">
          <option value="">Original ({width} × {height})</option>
          {sizes.map((s) => <option key={s} value={s}>Long edge {s}px</option>)}
        </select>
        <p className="mt-1 text-xs text-dim">Photos are never upscaled. Very large photos may be reduced to fit the server's limit, and you'll see a note if so.</p>
      </div>
      <button onClick={run} disabled={busy} className="mt-4 w-full rounded-xl bg-gold px-4 py-3 font-semibold text-ink hover:brightness-110 disabled:opacity-60">
        {busy ? "Exporting…" : "Download"}
      </button>
      <div aria-live="polite">
        {msg && <p className="mt-3 text-sm text-leaf">{msg}</p>}
        {err && <p role="alert" className="mt-3 text-sm text-alert">{err}</p>}
      </div>
    </section>
  );
}
