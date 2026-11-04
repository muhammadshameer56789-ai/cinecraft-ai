# CINECRAFT AI: API reference

All endpoints are under `/api`. Errors are JSON `{"detail": "<human-readable message>"}`. A cookie `cc_session` (HttpOnly, SameSite=Lax) is
issued automatically; every image, job and project is private to the session that created it. Requests for someone else's id return **404**
(never 403), so ids reveal nothing. Unexpected server errors return 500 with a reference id (`ref abcd1234`) that also appears in the server log.

Common status codes: `400` bad request / consent missing, `404` not found or not yours, `409` conflict (retry a non-failed job, project limit),
`413` too large, `415` unsupported format, `422` invalid input or unreadable image, `429` rate limited (`Retry-After` header), `503` AI not
configured or server busy (`Retry-After`), `507` out of memory for an export.

## Meta
| Method & path | Purpose |
|---|---|
| `GET /api/health` | `{status, editing_mode:"local", ai_provider:{configured,name}, limits}`. `configured` is true only when a provider is configured on the server. |
| `GET /api/privacy` | Plain-language retention, AI disclosure, training and cookie statements, with this server's real numbers. |
| `GET /api/presets` | The 10 presets: `[{id,name,purpose}]`. |

## Images
| Method & path | Body → Result |
|---|---|
| `POST /api/images/upload` | multipart `file` (JPEG/PNG/WebP, ≤ `MAX_UPLOAD_MB`, ≤ `MAX_PIXELS`) → `201 {image_id, format, width, height, size_bytes, retention_minutes, stored_on}`. Width/height are orientation-corrected. |
| `POST /api/images/analyze` | `{image_id}` → statistics (exposure, contrast, highlights, shadows, colour temperature, saturation, dominant colours, foliage, sky, skin area, faces, flags) and `suggested_adjustments`. |
| `GET /api/images/{id}/original` | The stored original. |
| `DELETE /api/images/{id}` | `204`. Removes the photo and its jobs. |
| `POST /api/images/edit` | `{image_id, preset, intensity 0-100, adjustments{15 sliders}, max_side 64-4096}` → `image/jpeg` preview (local engine). Headers: `X-Edit-Mode`, `X-Auto-Note`. |
| `GET /api/images/{id}/thumbnail/{preset}?size=180` | Small preview of a preset on this photo. |
| `POST /api/images/export` | `{image_id, preset, intensity, adjustments, format jpeg\|png\|webp, quality 1-100, max_side\|null}` → the file. Headers: `Content-Disposition` (e.g. `trip-cinecraft-golden-hour-80pct.jpg`), `X-Export-Width/Height`, `X-Export-Notes` (e.g. "Not upscaled…", "Reduced to … to stay within the server's … MP export limit"). sRGB profile embedded. |

Adjustment sliders (all default 0): `exposure brightness contrast highlights shadows temperature tint saturation vibrance green_intensity golden_intensity`
(−100…100) and `sharpness fade vignette grain` (0…100). They layer on top of the preset and are not scaled by `intensity`.

## Jobs (background editing, AI)
| Method & path | Purpose |
|---|---|
| `POST /api/images/jobs` | `{image_id, preset, intensity, adjustments, mode:"local"\|"ai", fallback_to_local:true, ai_consent:false}` → `202` job. `mode:"ai"` needs a configured provider (else `503`) **and** `ai_consent:true` (else `400`). Submitting identical work while a job is active returns the existing job. |
| `GET /api/images/jobs/{job_id}` | `{status: queued\|running\|succeeded\|failed, stage, error, error_kind, mode_used: local\|ai\|local-fallback, warning, attempts, retryable, has_result}`. `stage` is the real current step (e.g. "AI service is rate-limiting; retrying in 5s"); no invented percentages. |
| `GET /api/images/jobs/{job_id}/result` | `image/jpeg` (`409` while running). AI results are at most 1536 px on the long edge. |
| `POST /api/images/jobs/{job_id}/retry` | `202` new job from a **failed** job; `409` otherwise. |

`error_kind`: `not_configured, rate_limit, timeout, server, auth, bad_request, invalid_output, busy, not_found, internal`.
An AI result is rejected (`invalid_output`) if it is not a valid image or its coarse layout no longer matches the photo (composition guard).

## Projects (saved per browser session; no accounts)
| Method & path | Purpose |
|---|---|
| `POST /api/projects` | `{image_id, name, preset, intensity, adjustments}` → `201` project. Copies the original into project storage. |
| `GET /api/projects` | `{projects, retention_days, note}`. |
| `GET/PATCH/DELETE /api/projects/{id}` | Read, update (`name`, `preset`, `intensity`, `adjustments`), delete (`204`, also deletes files). |
| `GET /api/projects/{id}/original` · `/preview?size=` | Original / freshly rendered edited preview. |
| `POST /api/projects/{id}/open` | Copies the saved original into a new working image id and returns it with the project settings. |
| `POST /api/projects/{id}/export` | `{format, quality, max_side}` → file, using the saved settings. |
