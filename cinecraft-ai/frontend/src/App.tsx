import { useEffect, useRef, useState } from "react";
import { analyzeImage, deleteImage, getHealth, getPresets, openProject, originalUrl, renderEdit, uploadImage } from "./api";
import { ADJUSTMENTS, DEFAULT_STATE, ZERO_ADJUSTMENTS, type Adjustments, type AdjKey } from "./adjustments";
import { BRAND } from "./config";
import AdjustPanel from "./components/AdjustPanel";
import AiPanel, { type AiResult } from "./components/AiPanel";
import AnalysisPanel from "./components/AnalysisPanel";
import ComparisonViewer, { type ViewMode } from "./components/ComparisonViewer";
import ExportPanel from "./components/ExportPanel";
import PresetPanel from "./components/PresetPanel";
import PrivacyDialog from "./components/PrivacyDialog";
import ProjectsView from "./components/ProjectsView";
import SaveProject from "./components/SaveProject";
import UploadZone from "./components/UploadZone";
import { useEditHistory } from "./useEditHistory";
import type { Analysis, Health, PresetInfo, ProjectInfo, UploadResult } from "./types";

const MODES: { id: ViewMode; label: string }[] = [
  { id: "split", label: "Split" }, { id: "side", label: "Side by side" },
  { id: "edited", label: "Edited" }, { id: "original", label: "Original" },
];

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [presets, setPresets] = useState<PresetInfo[]>([]);
  const [view, setView] = useState<"editor" | "projects">("editor");
  const [showPrivacy, setShowPrivacy] = useState(false);
  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [mode, setMode] = useState<ViewMode>("split");
  const [tab, setTab] = useState<"styles" | "adjust">("styles");
  const [editedUrl, setEditedUrl] = useState<string | null>(null);
  const [ai, setAi] = useState<AiResult | null>(null);
  const [source, setSource] = useState<"local" | "ai">("local");
  const [autoNote, setAutoNote] = useState("");
  const [rendering, setRendering] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ctl = useRef<AbortController | null>(null);
  const h = useEditHistory(DEFAULT_STATE);
  const edit = h.state;

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setError("Cannot reach the server. Start the backend and reload."));
    getPresets().then(setPresets).catch(() => undefined);
  }, []);

  // Re-render the local preview whenever style, intensity or adjustments change (debounced; stale requests aborted).
  useEffect(() => {
    if (!upload || !analysis) return;
    const id = upload.image_id;
    const timer = setTimeout(async () => {
      ctl.current?.abort();
      const c = new AbortController();
      ctl.current = c;
      setRendering(true);
      try {
        const r = await renderEdit(id, edit, c.signal);
        setEditedUrl((old) => { if (old) URL.revokeObjectURL(old); return r.url; });
        setAutoNote(r.note); setError(null);
      } catch (e) {
        if ((e as Error).name !== "AbortError") setError(e instanceof Error ? e.message : "Preview failed. Try again.");
      } finally { if (ctl.current === c) setRendering(false); }
    }, 250);
    return () => clearTimeout(timer);
  }, [upload, analysis, edit]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || view !== "editor") return;
      const k = e.key.toLowerCase();
      if (k === "z" && !e.shiftKey) { e.preventDefault(); h.undo(); }
      else if ((k === "z" && e.shiftKey) || k === "y") { e.preventDefault(); h.redo(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [h.undo, h.redo, view]);

  const clearAi = () => { setAi((o) => { if (o) URL.revokeObjectURL(o.url); return null; }); setSource("local"); };

  async function loadPhoto(up: UploadResult, settings?: typeof DEFAULT_STATE) {
    h.reset(settings ?? DEFAULT_STATE); setEditedUrl(null); clearAi(); setAnalysis(null); setUpload(up);
    setAnalysis(await analyzeImage(up.image_id));
  }

  async function handleFile(file: File) {
    setBusy(true); setError(null);
    try {
      if (upload) await deleteImage(upload.image_id).catch(() => undefined);
      setProject(null);
      await loadPhoto(await uploadImage(file));
    } catch (e) {
      setUpload(null); setAnalysis(null);
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally { setBusy(false); }
  }

  async function handleOpenProject(id: string) {
    setError(null);
    if (upload) await deleteImage(upload.image_id).catch(() => undefined);
    const r = await openProject(id);
    setProject(r.project);
    setView("editor");
    await loadPhoto(r, { preset: r.project.preset, intensity: r.project.intensity, adjustments: { ...ZERO_ADJUSTMENTS, ...r.project.adjustments } as Adjustments });
  }

  async function remove() {
    ctl.current?.abort();
    if (upload) await deleteImage(upload.image_id).catch(() => undefined);
    setUpload(null); setAnalysis(null); setEditedUrl(null); setProject(null); clearAi(); setError(null); h.reset(DEFAULT_STATE);
  }

  const setAdj = (key: AdjKey, value: number) => h.transient({ ...edit, adjustments: { ...edit.adjustments, [key]: value } });
  const resetAdj = (key?: AdjKey) => h.apply({ ...edit, adjustments: key ? { ...edit.adjustments, [key]: 0 } : ZERO_ADJUSTMENTS });
  const selected = presets.find((p) => p.id === edit.preset);
  const aiFresh = !!ai && ai.key === JSON.stringify(edit);   // an AI result belongs to the exact settings it was made with
  const viewerEdited = source === "ai" && aiFresh ? ai!.url : editedUrl;
  const btn = (on: boolean) => `rounded-lg border px-3 py-1.5 text-sm ${on ? "border-gold text-gold" : "border-edge text-mist hover:border-dim"}`;

  return (
    <div className="mx-auto min-h-screen max-w-[1500px] px-5 py-6">
      <header className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <h1 className="text-xl font-bold tracking-wide">{BRAND.name}</h1>
        <nav className="flex gap-2" aria-label="Main">
          <button className={btn(view === "editor")} aria-current={view === "editor"} onClick={() => setView("editor")}>Photo Editor</button>
          <button className={btn(view === "projects")} aria-current={view === "projects"} onClick={() => setView("projects")}>My Projects</button>
        </nav>
        <span className="ml-auto text-sm text-dim">
          {health ? (health.ai_provider.configured ? `AI available: ${health.ai_provider.name} · local editing` : "Local editing mode, no AI provider configured") : ""}
        </span>
        <button className="text-sm text-dim underline hover:text-mist" onClick={() => setShowPrivacy(true)}>Privacy</button>
      </header>
      {showPrivacy && <PrivacyDialog onClose={() => setShowPrivacy(false)} />}

      {view === "projects" ? <ProjectsView onOpen={handleOpenProject} /> : !upload ? (
        <main className="mt-14 max-w-2xl">
          <h2 className="text-4xl font-bold leading-tight">Transform Your Photos Into Cinematic Masterpieces</h2>
          <p className="mt-3 mb-8 text-lg text-dim">Upload a photo, choose your aesthetic, and let AI enhance your image automatically.</p>
          <UploadZone busy={busy} error={error} onFile={handleFile} onClientError={setError} />
        </main>
      ) : (
        <main className="mt-6 grid gap-6 lg:grid-cols-[270px_1fr_330px]">
          <div className="order-2 lg:order-1 lg:max-h-[calc(100vh-110px)] lg:overflow-y-auto lg:pr-1">
            <div className="mb-3 flex gap-2" role="tablist">
              <button role="tab" aria-selected={tab === "styles"} className={btn(tab === "styles")} onClick={() => setTab("styles")}>Styles</button>
              <button role="tab" aria-selected={tab === "adjust"} className={btn(tab === "adjust")} onClick={() => setTab("adjust")}>
                Adjust{ADJUSTMENTS.some((a) => edit.adjustments[a.key] !== 0) ? " •" : ""}
              </button>
            </div>
            {tab === "styles"
              ? <PresetPanel imageId={upload.image_id} presets={presets} selected={edit.preset} onSelect={(id) => h.apply({ ...edit, preset: id })} />
              : <AdjustPanel values={edit.adjustments} onChange={setAdj} onCommit={h.commit} onReset={resetAdj} />}
          </div>

          <section className="order-1 min-w-0 lg:order-2">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <div className="flex gap-2" role="group" aria-label="View mode">
                {MODES.map((m) => <button key={m.id} aria-pressed={mode === m.id} className={btn(mode === m.id)} onClick={() => setMode(m.id)}>{m.label}</button>)}
              </div>
              {aiFresh && (
                <div className="flex gap-2" role="group" aria-label="Edited version">
                  <button className={btn(source === "local")} aria-pressed={source === "local"} onClick={() => setSource("local")}>Local edit</button>
                  <button className={btn(source === "ai")} aria-pressed={source === "ai"} onClick={() => setSource("ai")}>{ai!.modeUsed === "ai" ? "AI result" : "Fallback result"}</button>
                </div>
              )}
              <div className="ml-auto flex gap-2">
                <button className={`${btn(false)} disabled:opacity-40`} disabled={!h.canUndo} onClick={h.undo} title="Undo (Ctrl+Z)">Undo</button>
                <button className={`${btn(false)} disabled:opacity-40`} disabled={!h.canRedo} onClick={h.redo} title="Redo (Ctrl+Shift+Z)">Redo</button>
              </div>
            </div>

            <ComparisonViewer originalUrl={originalUrl(upload.image_id)} editedUrl={viewerEdited} rendering={rendering || busy} mode={mode} />
            {source === "ai" && aiFresh && <p className="mt-2 text-xs text-dim">Showing the {ai!.modeUsed === "ai" ? "AI-generated" : "fallback"} result at up to 1536 px. Export below applies to the local edit. Right-click the viewer image to save the AI result.</p>}
            {ai && !aiFresh && <p className="mt-2 text-xs text-gold">Settings changed since the AI result was made. Showing the local edit; generate again to refresh the AI version.</p>}

            <div className="mt-4 rounded-2xl bg-panel p-4">
              <div className="flex items-center justify-between">
                <label htmlFor="intensity" className="font-semibold">Style intensity</label>
                <output className="tabular-nums text-gold">{edit.intensity}%</output>
              </div>
              <input id="intensity" type="range" min={0} max={100} value={edit.intensity} className="mt-2 w-full accent-[#d9a441]"
                onChange={(e) => h.transient({ ...edit, intensity: +e.target.value })} onPointerUp={h.commit} onKeyUp={h.commit} onBlur={h.commit} />
              {edit.preset === "auto_cinematic" && autoNote && <p className="mt-2 text-sm text-dim">Auto choice: {autoNote}</p>}
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-dim">
              <span>{upload.width} × {upload.height} · {upload.format} · {(upload.size_bytes / 1048576).toFixed(1)} MB</span>
              <label className="cursor-pointer rounded-lg border border-edge px-3 py-1.5 text-mist hover:border-dim">
                Replace photo
                <input type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); e.target.value = ""; }} />
              </label>
              <button onClick={remove} className="rounded-lg border border-edge px-3 py-1.5 text-mist hover:border-alert hover:text-alert">Remove photo</button>
              <span className="ml-auto">Working copy kept {upload.retention_minutes} min after last use. Save a project to keep it longer.</span>
            </div>
            {error && <p role="alert" className="mt-3 rounded-lg border border-alert/50 bg-alert/10 px-4 py-3 text-alert">{error}</p>}
          </section>

          <aside className="order-3 space-y-4">
            {selected && (
              <section className="rounded-2xl bg-panel p-5">
                <h2 className="text-lg font-semibold">{selected.name}</h2>
                <p className="mt-1 text-sm text-dim">{selected.purpose}</p>
              </section>
            )}
            <ExportPanel imageId={upload.image_id} edit={edit} width={upload.width} height={upload.height} />
            <AiPanel imageId={upload.image_id} edit={edit} health={health} onResult={(r) => { setAi((o) => { if (o) URL.revokeObjectURL(o.url); return r; }); setSource(r ? "ai" : "local"); }} />
            <SaveProject imageId={upload.image_id} edit={edit} project={project} defaultName={`Project ${new Date().toLocaleDateString()}`} onSaved={setProject} />
            {analysis
              ? <details className="rounded-2xl"><summary className="cursor-pointer rounded-2xl bg-panel px-5 py-3 font-semibold">Photo analysis</summary><div className="mt-2"><AnalysisPanel a={analysis} /></div></details>
              : <p className="rounded-2xl bg-panel p-5 text-dim">{busy ? "Analysing photo…" : "No analysis yet."}</p>}
          </aside>
        </main>
      )}
    </div>
  );
}
