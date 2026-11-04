export const ADJUSTMENTS = [
  { key: "exposure", label: "Exposure", min: -100, max: 100 },
  { key: "brightness", label: "Brightness", min: -100, max: 100 },
  { key: "contrast", label: "Contrast", min: -100, max: 100 },
  { key: "highlights", label: "Highlights", min: -100, max: 100 },
  { key: "shadows", label: "Shadows", min: -100, max: 100 },
  { key: "temperature", label: "Temperature", min: -100, max: 100 },
  { key: "tint", label: "Tint", min: -100, max: 100 },
  { key: "saturation", label: "Saturation", min: -100, max: 100 },
  { key: "vibrance", label: "Vibrance", min: -100, max: 100 },
  { key: "sharpness", label: "Sharpness", min: 0, max: 100 },
  { key: "fade", label: "Fade", min: 0, max: 100 },
  { key: "vignette", label: "Vignette", min: 0, max: 100 },
  { key: "grain", label: "Grain", min: 0, max: 100 },
  { key: "green_intensity", label: "Green intensity", min: -100, max: 100 },
  { key: "golden_intensity", label: "Golden highlights", min: -100, max: 100 },
] as const;

export type AdjKey = (typeof ADJUSTMENTS)[number]["key"];
export type Adjustments = Record<AdjKey, number>;

export const ZERO_ADJUSTMENTS = Object.fromEntries(ADJUSTMENTS.map((a) => [a.key, 0])) as Adjustments;

/** Everything the user can change. Undo/redo operates on this whole object. */
export interface EditState { preset: string; intensity: number; adjustments: Adjustments }
export const DEFAULT_STATE: EditState = { preset: "auto_cinematic", intensity: 70, adjustments: ZERO_ADJUSTMENTS };
export const hasAdjustments = (a: Adjustments) => Object.values(a).some((v) => v !== 0);
