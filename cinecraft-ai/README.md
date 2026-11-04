# CINECRAFT AI: Your Photos. Cinematic Perfection.

A web app that analyses a photo and gives it a cinematic grade using a real image-processing engine (NumPy + OpenCV), with ten adaptive
presets, an intensity control, manual adjustments with undo/redo, before/after comparison, export, saved projects, and an optional,
consent-gated AI image-editing adapter.

## What is implemented vs. what needs something external

| Feature | Status |
|---|---|
| Upload + validation (type, size, megapixels, corruption), EXIF orientation | Implemented, tested |
| Photo analysis (exposure, contrast, highlights, shadows, temperature, saturation, colours, foliage, sky, skin area, faces) driving the edit | Implemented, tested |
| Local editing engine, 10 presets, adaptive parameters, intensity (parameter interpolation) | Implemented, tested |
| Skin protection, shadow-detail guard (keeps texture in dark clothing) | Implemented, tested |
| 15 manual sliders, reset, undo/redo, defined layering rule | Implemented; backend + history logic tested |
| Before/after viewer (split, side-by-side, zoom, touch) | Implemented; **not run in a browser by the authors** |
| Export JPEG/PNG/WebP, quality, resize, original size, sRGB profile, safe filenames | Implemented, tested |
| Async jobs with real stages, retry, rate-limit handling, local fallback, duplicate prevention | Implemented, tested with a simulated provider |
| **AI image editing** | Adapter implemented (OpenAI-style `images/edits`) and tested against a **local fake server only**. **Not verified against the live service.** Requires your own provider account/key. Run `scripts/check_ai_provider.py` to verify. Not configured by default; the UI says so. |
| Projects (save/open/rename/delete/export) | Implemented, tested. Tied to an anonymous browser session, **not user accounts** |
| User accounts / login / subscriptions / pricing | **Not implemented** (no nonfunctional nav items are shown) |
| Person segmentation model | **Not implemented**; skin protection uses colour rules + optional face boxes |
| Rate limiting, per-session authorisation, retention cleanup, security headers | Implemented; HTTP layer covered by `tests/test_api_integration.py` which needs FastAPI installed (see Testing) |

## Project structure
```
backend/app/
  main.py            app, session cookie + security-header middleware, janitor, health/privacy
  config.py          all settings (environment variables)
  security.py        session owner, rate-limit dependency
  state.py           singletons (jobs, projects, limiter)
  routers/           images, edit (preview/export/thumbnail), jobs, projects
  services/
    validation.py    decode/verify, size + pixel limits
    storage.py       generated ids, owner check, retention
    analysis.py      photo analysis → suggested_adjustments
    presets.py       10 presets (Look), blend, intensity scaling
    adaptation.py    preset + analysis → actual parameters; Auto Cinematic selection
    engine.py        the image pipeline
    manual.py        15 manual sliders layered on the preset
    exporter.py      export (formats, sizes, memory guard, ICC)
    jobs.py          async jobs, retries, fallback
    projects.py      SQLite project store (owner-scoped)
    limits.py ratelimit.py sessions.py
    ai/              base, prompts, canvas (letterbox), guard (composition check), openai_provider
backend/scripts/     check_ai_provider.py, acceptance_AJ.py
backend/tests/       unit + integration tests
frontend/src/        React + TypeScript + Vite + Tailwind
docs/API.md          endpoint reference        deploy/   sample Dockerfile + nginx (untested)
```

## Install and run (development)
Requirements: Python 3.11+, Node 18+.
```
cd backend
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt httpx
cp .env.example .env                                      # optional; defaults work. Export variables or use your process manager to load it.
uvicorn app.main:app --reload --port 8000

cd frontend
npm install
npm run dev                                               # http://localhost:5173 (proxies /api to :8000)
```

## Production
1. `cd frontend && npm run build` → static files in `frontend/dist`.
2. Run the API behind HTTPS on the **same origin** as the frontend (see `deploy/nginx.conf.example`). Set `COOKIE_SECURE=true`, and `TRUSTED_PROXY=true` only if your proxy sets `X-Forwarded-For`.
3. Start with **one** worker: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`. Jobs, rate limits and the render slot live in process memory.
4. Persist `DB_PATH`, `PROJECT_DIR` (and optionally `STORAGE_DIR`) on a volume.
5. **Size RAM**: a full-size render needs about **150 MB per megapixel** (measured: 12 MP peaked near 2 GB). `EXPORT_MAX_PIXELS` (default 12 MP) caps it; `HEAVY_CONCURRENCY` (default 1) limits simultaneous full renders. Larger exports are reduced with a visible note.
6. Scaling out (several workers/servers) needs a shared job store, rate limiter and storage (e.g. Redis + object storage); not included.

## Environment variables (`backend/.env.example`)
| Variable | Default | Meaning |
|---|---|---|
| `MAX_UPLOAD_MB` / `MAX_PIXELS` | 20 / 60000000 | Upload limits (also decompression-bomb guard) |
| `EXPORT_MAX_PIXELS` | 12000000 | Largest single-pass export (RAM guard) |
| `HEAVY_CONCURRENCY` | 1 | Simultaneous full-size renders |
| `STORAGE_DIR` / `RETENTION_MINUTES` | ./storage / 60 | Working copies; deleted this long after last use |
| `PROJECT_DIR` / `DB_PATH` / `PROJECT_RETENTION_DAYS` / `MAX_PROJECTS_PER_SESSION` | ./data/… / 14 / 50 | Saved projects |
| `JOB_TTL_MINUTES` | 30 | How long finished jobs and results are kept |
| `COOKIE_SECURE` / `TRUSTED_PROXY` | false / false | Set true behind HTTPS / a header-setting proxy |
| `CORS_ORIGINS` | http://localhost:5173 | Only needed if frontend and API are on different origins |
| `AI_PROVIDER` | empty | `openai` to enable AI mode; empty = local only |
| `AI_API_KEY` | empty | Server-side only; never sent to the browser |
| `AI_MODEL` / `AI_BASE_URL` / `AI_TIMEOUT_S` / `AI_MAX_RETRIES` / `AI_MIN_SIMILARITY` | gpt-image-1 / https://api.openai.com / 120 / 2 / 0.55 | Provider options; `AI_BASE_URL` works for OpenAI-compatible gateways |

## AI provider setup
1. Set `AI_PROVIDER=openai` and `AI_API_KEY=…` (and `AI_MODEL` if needed), restart the API. `GET /api/health` now reports the provider; the UI shows the AI panel.
2. **Verify it yourself**: `cd backend && AI_PROVIDER=openai AI_API_KEY=sk-… python scripts/check_ai_provider.py [photo.jpg]`. It sends one photo, prints the composition-similarity score and writes `ai_check_output.jpg`. Inspect it for identity and framing.
3. How a job works: the user must tick a consent box → the photo is downsized (≤1536 px) and letterboxed onto a supported canvas → the preset-specific prompt (identity preservation, analysis hints) is sent → the result is validated, cropped back to the original framing, and checked against the original's layout → rejected results are retried or, if allowed, replaced by the labelled local result.
4. To add another provider, implement `AIProvider.edit(image_png, prompt, size) -> bytes` in `services/ai/` and return it from `get_provider()`.
5. Limits: AI results are provider-resolution (≤1536 px), the exported file always comes from the local engine, and **no identity-preservation guarantee** exists beyond the prompt and the coarse composition check. Review AI results before using them.

## Testing
```
cd backend && python -m unittest discover tests -v           # 83 tests (8 need FastAPI and are skipped without it)
cd backend && pip install httpx && python -m unittest tests.test_api_integration -v   # HTTP-level tests; run these once on your machine
cd frontend && npm test                                       # undo/redo logic (7 tests)
cd backend && python scripts/acceptance_AJ.py --green g.jpg --dark-clothes d.jpg --sky s.jpg --warm w.jpg --dusk u.jpg --sheet out.png
```
`acceptance_AJ.py` runs spec tests A–J on photos you supply and prints a pass/fail line with the measured numbers for each; tests whose photo is
missing are skipped. Harsh-light, underexposed, low-resolution and large photos are derived from `--dark-clothes`.

Results on the 4 reference photos supplied with the brief (11/11 passed): A greens shifted 18° toward gold with skin hue drift 2.5°; B clipped
highlights 34%→0%; C underexposed lifted ×1.29 with noise ×1.04; D dark-clothing local detail kept (0.96 fine / 1.00 fold scale); E sky hue unchanged
and unclipped; F/G no added warmth on a dusk/warm photo; H low-res kept at 200 px with a "not upscaled" note; I six corrupt/unsupported files all
rejected with 4xx; J 12 MP: preview 1.0 s, full export 8.4 s, peak ≈2 GB.

## Security and privacy summary
Server-side validation of every upload (format, size, pixel count, full decode); generated ids only, client filenames never touch the disk; every
image/job/project scoped to an unguessable session cookie (404 for anything else); per-IP rate limits; request-size guard; security headers;
secrets only in server environment; logs contain no file paths or request bodies; automatic cleanup of working copies, jobs and projects. Photos
are never sent anywhere unless the user ticks the AI consent box and a provider is configured. See `GET /api/privacy` (also shown in the app).

## Known limitations
- Verified in a browser by nobody yet: the React UI was type-checked against stubs, and its undo/redo logic was unit-tested, but it has not been built or clicked through. Expect small first-run fixes.
- `tests/test_api_integration.py` has never been executed (FastAPI could not be installed where it was written); the router handlers were exercised directly against stand-ins.
- Only the supplied 4 photos (and variants derived from them) were used for image-quality testing, and no real indoor photograph. Quality on other photographers' work is unproven.
- The AI adapter is untested against a live provider (see above). AI results are ≤1536 px and are not exportable as originals-size files.
- Projects have no accounts: clearing cookies or switching browsers loses access. Pricing/accounts are out of scope.
- Single-process design (see Production). Pinch-to-zoom is not implemented. Skin protection is colour-rule based; no segmentation model.
- Exports above `EXPORT_MAX_PIXELS` are reduced, not tiled.
