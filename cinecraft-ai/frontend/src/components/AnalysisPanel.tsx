import type { Analysis } from "../types";

const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

export default function AnalysisPanel({ a }: { a: Analysis }) {
  const rows: [string, string][] = [
    ["Exposure", `${a.exposure.label} (mean ${pct(a.exposure.mean_luminance)})`],
    ["Contrast", a.contrast.toFixed(3)],
    ["Highlights over 94%", pct(a.highlights.fraction_over_94pct)],
    ["Shadows under 10%", pct(a.shadows.fraction_under_10pct)],
    ["Colour temperature", `${a.color.temperature} (index ${a.color.warmth_index})`],
    ["Saturation", pct(a.color.saturation_mean)],
    ["Foliage coverage", pct(a.foliage.green_fraction)],
    ["Skin-tone area", pct(a.skin.fraction)],
    ["Faces", a.faces.available ? String(a.faces.count) : "detector unavailable"],
    ["Size", `${a.dimensions.width} × ${a.dimensions.height} (${a.dimensions.megapixels} MP, ${a.dimensions.orientation})`],
  ];
  return (
    <section className="rounded-2xl bg-panel p-5">
      <h2 className="text-lg font-semibold">What the analysis found</h2>
      <div className="mt-3 flex gap-2" aria-label="Dominant colours">
        {a.color.dominant_colors.map((c) => (
          <span key={c.hex} title={`${c.hex} · ${pct(c.share)}`} className="h-7 flex-1 rounded-md border border-edge" style={{ background: c.hex }} />
        ))}
      </div>
      <dl className="mt-4 divide-y divide-edge text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4 py-2"><dt className="text-dim">{k}</dt><dd className="text-right">{v}</dd></div>
        ))}
      </dl>
      {a.scene.length > 0 && <p className="mt-4 text-sm"><span className="text-dim">Detected: </span>{a.scene.join(", ")}</p>}
      {a.flags.low_resolution && <p className="mt-3 text-sm text-gold">Low-resolution photo. Edits will not add real detail.</p>}
      <p className="mt-4 text-xs text-dim">These numbers set the starting adjustments for Phase 2. Face detection and skin areas are estimates, and no segmentation model is loaded.</p>
    </section>
  );
}
