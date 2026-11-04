import { useEffect, useState } from "react";
import { deleteProject, exportProject, listProjects, projectPreviewUrl, updateProject } from "../api";
import type { ProjectInfo } from "../types";

interface Props { onOpen: (id: string) => Promise<void> }
const days = (t: number) => Math.max(0, Math.ceil((t * 1000 - Date.now()) / 86400000));

export default function ProjectsView({ onOpen }: Props) {
  const [items, setItems] = useState<ProjectInfo[] | null>(null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = () => listProjects().then((r) => { setItems(r.projects); setNote(r.note); }).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  async function act(id: string, fn: () => Promise<unknown>) {
    setBusy(id); setErr(null);
    try { await fn(); } catch (e) { setErr(e instanceof Error ? e.message : "Something went wrong."); } finally { setBusy(null); }
  }
  const download = (id: string) => act(id, async () => {
    const { blob, filename } = await exportProject(id, "jpeg");
    const url = URL.createObjectURL(blob), a = document.createElement("a");
    a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 10_000);
  });
  const remove = (p: ProjectInfo) => { if (confirm(`Delete "${p.name}"? This also deletes the saved original photo.`)) act(p.id, async () => { await deleteProject(p.id); await load(); }); };
  const rename = () => renaming && act(renaming.id, async () => { await updateProject(renaming.id, { name: renaming.name }); setRenaming(null); await load(); });

  const btn = "rounded-lg border border-edge px-2.5 py-1 text-sm hover:border-dim disabled:opacity-50";
  return (
    <main className="mt-8">
      <h2 className="text-2xl font-bold">My Projects</h2>
      <p className="mt-1 text-sm text-dim">{note}</p>
      {err && <p role="alert" className="mt-3 rounded-lg border border-alert/50 bg-alert/10 px-4 py-3 text-alert">{err}</p>}
      {items === null ? <p className="mt-6 text-dim">Loading…</p> : items.length === 0 ? (
        <p className="mt-6 rounded-2xl bg-panel p-6 text-dim">No saved projects yet. Edit a photo and choose “Save project”.</p>
      ) : (
        <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {items.map((p) => (
            <li key={p.id} className="overflow-hidden rounded-2xl bg-panel">
              <img src={projectPreviewUrl(p.id)} alt={`Edited preview of ${p.name}`} loading="lazy" className="aspect-[4/3] w-full bg-ink object-cover" />
              <div className="p-4">
                {renaming?.id === p.id ? (
                  <form onSubmit={(e) => { e.preventDefault(); rename(); }} className="flex gap-2">
                    <input autoFocus aria-label="Project name" value={renaming.name} maxLength={80} onChange={(e) => setRenaming({ id: p.id, name: e.target.value })} className="min-w-0 flex-1 rounded-lg border border-edge bg-ink px-2 py-1 text-sm" />
                    <button className={btn}>Save</button>
                  </form>
                ) : <h3 className="truncate font-semibold" title={p.name}>{p.name}</h3>}
                <p className="mt-1 text-xs text-dim">{p.preset.replace(/_/g, " ")} · {Math.round(p.intensity)}% · {p.width}×{p.height} · expires in {days(p.expires)} d</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button className={btn} disabled={busy === p.id} onClick={() => act(p.id, () => onOpen(p.id))}>Open</button>
                  <button className={btn} disabled={busy === p.id} onClick={() => download(p.id)}>Download</button>
                  <button className={btn} onClick={() => setRenaming({ id: p.id, name: p.name })}>Rename</button>
                  <button className={`${btn} hover:border-alert hover:text-alert`} disabled={busy === p.id} onClick={() => remove(p)}>Delete</button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
