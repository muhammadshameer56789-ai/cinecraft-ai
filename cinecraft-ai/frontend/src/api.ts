import type { EditState } from "./adjustments";
import type { Analysis, Health, JobInfo, PresetInfo, Privacy, ProjectInfo, UploadResult } from "./types";

async function parse<T>(res: Response): Promise<T> {
  if (res.ok) return res.status === 204 ? (undefined as T) : res.json();
  let msg = `Request failed (${res.status}).`;
  try { const body = await res.json(); if (typeof body.detail === "string") msg = body.detail; } catch { /* keep default */ }
  throw new Error(msg);
}

export const getHealth = () => fetch("/api/health").then(parse<Health>);

export function uploadImage(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  return fetch("/api/images/upload", { method: "POST", body: form }).then(parse<UploadResult>);
}

export const analyzeImage = (image_id: string) =>
  fetch("/api/images/analyze", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image_id }) }).then(parse<Analysis>);

export const deleteImage = (id: string) => fetch(`/api/images/${id}`, { method: "DELETE" }).then(parse<void>);
export const originalUrl = (id: string) => `/api/images/${id}/original`;

export const getPresets = () => fetch("/api/presets").then(parse<{ presets: PresetInfo[] }>).then((r) => r.presets);
export const thumbnailUrl = (id: string, preset: string) => `/api/images/${id}/thumbnail/${preset}?size=180`;

export async function renderEdit(image_id: string, s: EditState, signal: AbortSignal) {
  const res = await fetch("/api/images/edit", { method: "POST", signal, headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image_id, preset: s.preset, intensity: s.intensity, adjustments: s.adjustments, max_side: 1400 }) });
  if (!res.ok) await parse<never>(res);
  return { url: URL.createObjectURL(await res.blob()), note: res.headers.get("X-Auto-Note") || "" };
}

export interface ExportOptions { format: "jpeg" | "png" | "webp"; quality: number; max_side: number | null }
export interface ExportOutput { blob: Blob; filename: string; width: number; height: number; notes: string }

export async function exportImage(image_id: string, s: EditState, o: ExportOptions): Promise<ExportOutput> {
  const res = await fetch("/api/images/export", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image_id, preset: s.preset, intensity: s.intensity, adjustments: s.adjustments, ...o }) });
  if (!res.ok) await parse<never>(res);
  const cd = res.headers.get("Content-Disposition") || "";
  return {
    blob: await res.blob(),
    filename: /filename="([^"]+)"/.exec(cd)?.[1] ?? `photo.${o.format === "jpeg" ? "jpg" : o.format}`,
    width: Number(res.headers.get("X-Export-Width")), height: Number(res.headers.get("X-Export-Height")),
    notes: res.headers.get("X-Export-Notes") || "",
  };
}

// ---- jobs (AI / background editing) ----
const json = (body: unknown) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const createJob = (image_id: string, s: EditState, o: { mode: "local" | "ai"; fallback_to_local: boolean; ai_consent: boolean }) =>
  fetch("/api/images/jobs", json({ image_id, preset: s.preset, intensity: s.intensity, adjustments: s.adjustments, ...o })).then(parse<JobInfo>);
export const getJob = (id: string) => fetch(`/api/images/jobs/${id}`).then(parse<JobInfo>);
export const retryJob = (id: string) => fetch(`/api/images/jobs/${id}/retry`, { method: "POST" }).then(parse<JobInfo>);
export const jobResultUrl = async (id: string) => {
  const res = await fetch(`/api/images/jobs/${id}/result`);
  if (!res.ok) await parse<never>(res);
  return URL.createObjectURL(await res.blob());
};

// ---- projects ----
export const getPrivacy = () => fetch("/api/privacy").then(parse<Privacy>);
export const listProjects = () => fetch("/api/projects").then(parse<{ projects: ProjectInfo[]; retention_days: number; note: string }>);
export const saveProject = (image_id: string, name: string, s: EditState) =>
  fetch("/api/projects", json({ image_id, name, preset: s.preset, intensity: s.intensity, adjustments: s.adjustments })).then(parse<ProjectInfo>);
export const updateProject = (id: string, body: Partial<{ name: string; preset: string; intensity: number; adjustments: unknown }>) =>
  fetch(`/api/projects/${id}`, { ...json(body), method: "PATCH" }).then(parse<ProjectInfo>);
export const deleteProject = (id: string) => fetch(`/api/projects/${id}`, { method: "DELETE" }).then(parse<void>);
export const openProject = (id: string) => fetch(`/api/projects/${id}/open`, { method: "POST" }).then(parse<UploadResult & { project: ProjectInfo }>);
export const projectPreviewUrl = (id: string, size = 360) => `/api/projects/${id}/preview?size=${size}`;
export async function exportProject(id: string, format: "jpeg" | "png" | "webp", quality = 92) {
  const res = await fetch(`/api/projects/${id}/export`, json({ format, quality, max_side: null }));
  if (!res.ok) await parse<never>(res);
  const cd = res.headers.get("Content-Disposition") || "";
  return { blob: await res.blob(), filename: /filename="([^"]+)"/.exec(cd)?.[1] ?? `project.${format}` };
}
