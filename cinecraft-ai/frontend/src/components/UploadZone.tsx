import { useRef, useState } from "react";
import { ACCEPTED, MAX_MB } from "../config";

interface Props { busy: boolean; error: string | null; onFile: (f: File) => void; onClientError: (m: string) => void }

export default function UploadZone({ busy, error, onFile, onClientError }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  function pick(file?: File) {
    if (!file) return;
    if (!ACCEPTED.includes(file.type)) return onClientError("Unsupported format. Use JPEG, PNG or WebP.");
    if (file.size > MAX_MB * 1024 * 1024) return onClientError(`This file is larger than ${MAX_MB} MB. Choose a smaller photo.`);
    onFile(file);
  }

  return (
    <div>
      <div
        role="button" tabIndex={0} aria-busy={busy}
        onClick={() => !busy && input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && !busy && input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files[0]); }}
        className={`flex min-h-[320px] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 text-center transition-colors
          ${drag ? "border-gold bg-gold/10" : "border-edge bg-panel hover:border-dim"}`}
      >
        <p className="text-xl font-semibold">{busy ? "Uploading and analysing…" : "Drop a photo here"}</p>
        <p className="mt-2 text-dim">{busy ? "Reading exposure, colour and light." : "or click to browse. JPEG, PNG or WebP, up to 20 MB."}</p>
        <input ref={input} type="file" accept={ACCEPTED.join(",")} hidden onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
      </div>
      <p className="mt-3 text-sm text-dim">Your photo is sent to this app's own server for analysis and kept temporarily. It is not sent to any third-party service.</p>
      {error && <p role="alert" className="mt-3 rounded-lg border border-alert/50 bg-alert/10 px-4 py-3 text-alert">{error}</p>}
    </div>
  );
}
