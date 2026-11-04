import { useEffect, useState } from "react";
import { getPrivacy } from "../api";
import type { Privacy } from "../types";

export default function PrivacyDialog({ onClose }: { onClose: () => void }) {
  const [p, setP] = useState<Privacy | null>(null);
  useEffect(() => { getPrivacy().then(setP).catch(() => undefined); const k = (e: KeyboardEvent) => e.key === "Escape" && onClose(); window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [onClose]);
  return (
    <div role="dialog" aria-modal="true" aria-label="Privacy" className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-panel p-6" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-xl font-bold">Privacy</h2>
        {p ? <dl className="mt-4 space-y-3 text-sm">
          {([["Your uploads", p.uploads], ["Saved projects", p.projects], ["AI mode", p.ai], ["Model training", p.training], ["Cookies", p.cookies]] as const).map(([k, v]) => (
            <div key={k}><dt className="font-semibold">{k}</dt><dd className="text-dim">{v}</dd></div>))}
        </dl> : <p className="mt-4 text-dim">Loading…</p>}
        <button autoFocus onClick={onClose} className="mt-5 rounded-lg border border-edge px-4 py-2 text-sm hover:border-dim">Close</button>
      </div>
    </div>
  );
}
