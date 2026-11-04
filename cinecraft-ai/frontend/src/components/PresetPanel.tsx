import { thumbnailUrl } from "../api";
import type { PresetInfo } from "../types";

interface Props { imageId: string; presets: PresetInfo[]; selected: string; onSelect: (id: string) => void }

export default function PresetPanel({ imageId, presets, selected, onSelect }: Props) {
  return (
    <section aria-label="Editing styles">
      <h2 className="mb-3 text-lg font-semibold">Styles</h2>
      <div className="grid grid-cols-3 gap-2 lg:grid-cols-2">
        {presets.map((p) => (
          <button key={p.id} onClick={() => onSelect(p.id)} aria-pressed={selected === p.id} title={p.purpose}
            className={`overflow-hidden rounded-xl border-2 bg-panel text-left transition-colors ${selected === p.id ? "border-gold" : "border-transparent hover:border-edge"}`}>
            <img src={thumbnailUrl(imageId, p.id)} alt="" loading="lazy" className="aspect-[4/3] w-full object-cover" />
            <span className="block px-2 py-1.5 text-sm font-medium">{p.name}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
