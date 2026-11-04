export interface UploadResult {
  image_id: string; format: string; width: number; height: number;
  size_bytes: number; retention_minutes: number; stored_on: string;
}
export interface Analysis {
  dimensions: { width: number; height: number; megapixels: number; orientation: string };
  exposure: { label: string; mean_luminance: number };
  contrast: number;
  highlights: { fraction_over_94pct: number; clipped_white_fraction: number };
  shadows: { fraction_under_10pct: number };
  color: { temperature: string; warmth_index: number; saturation_mean: number; dominant_colors: { hex: string; share: number }[] };
  foliage: { green_fraction: number };
  skin: { fraction: number; note: string };
  faces: { available: boolean; count: number | null };
  subject_separation: { score: number; note: string };
  scene: string[];
  flags: { low_resolution: boolean };
  suggested_adjustments: Record<string, unknown>;
}
export interface Health { editing_mode: string; ai_provider: { configured: boolean; name: string | null } }
export interface PresetInfo { id: string; name: string; purpose: string }
export interface JobInfo {
  job_id: string; status: "queued" | "running" | "succeeded" | "failed"; stage: string; error: string | null; error_kind: string | null;
  mode_requested: string; mode_used: string | null; warning: string | null; attempts: number; has_result: boolean; retryable: boolean;
}
export interface ProjectInfo {
  id: string; name: string; preset: string; intensity: number; adjustments: Record<string, number>;
  width: number; height: number; created: number; updated: number; expires: number; stem: string; ext: string;
}
export interface Privacy { uploads: string; projects: string; ai: string; training: string; cookies: string }
