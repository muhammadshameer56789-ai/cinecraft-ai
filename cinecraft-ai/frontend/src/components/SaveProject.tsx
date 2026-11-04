import { useEffect, useState } from "react";
import { saveProject, updateProject } from "../api";
import type { EditState } from "../adjustments";
import type { ProjectInfo } from "../types";

interface Props { imageId: string; edit: EditState; project: ProjectInfo | null; defaultName: string; onSaved: (p: ProjectInfo) => void }

export default function SaveProject({ imageId, edit, project, defaultName, onSaved }: Props) {
  const [name, setName] = useState(project?.name ?? defaultName);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setName(project?.name ?? defaultName); setMsg(null); }, [project?.id, defaultName]);

  async function save(asNew: boolean) {
    setBusy(true); setErr(null); setMsg(null);
    try {
      const p = project && !asNew
        ? await updateProject(project.id, { name, preset: edit.preset, intensity: edit.intensity, adjustments: edit.adjustments })
        : await saveProject(imageId, name, edit);
      onSaved(p); setMsg(project && !asNew ? "Project updated." : "Project saved.");
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not save."); } finally { setBusy(false); }
  }
  return (
    <section className="rounded-2xl bg-panel p-5" aria-label="Save project">
      <h2 className="text-lg font-semibold">Project</h2>
      <label htmlFor="pname" className="mt-2 block text-sm text-dim">Name</label>
      <input id="pname" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} className="mt-1 w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm" />
      <div className="mt-3 flex gap-2">
        <button onClick={() => save(false)} disabled={busy || !name.trim()} className="flex-1 rounded-lg bg-gold px-3 py-2 text-sm font-semibold text-ink disabled:opacity-50">{project ? "Update project" : "Save project"}</button>
        {project && <button onClick={() => save(true)} disabled={busy || !name.trim()} className="rounded-lg border border-edge px-3 py-2 text-sm hover:border-dim disabled:opacity-50">Save as new</button>}
      </div>
      <p className="mt-2 text-xs text-dim">Saved on this server for this browser only (no account) and deleted after a period of inactivity. Clearing cookies loses access.</p>
      {msg && <p className="mt-2 text-sm text-leaf" aria-live="polite">{msg}</p>}
      {err && <p role="alert" className="mt-2 text-sm text-alert">{err}</p>}
    </section>
  );
}
