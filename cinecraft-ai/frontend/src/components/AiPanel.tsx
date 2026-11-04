import { useEffect, useRef, useState } from "react";
import { createJob, getJob, jobResultUrl, retryJob } from "../api";
import type { EditState } from "../adjustments";
import type { Health, JobInfo } from "../types";

export interface AiResult { url: string; modeUsed: string; warning: string | null; key: string }
interface Props { imageId: string; edit: EditState; health: Health | null; onResult: (r: AiResult | null) => void }

export default function AiPanel({ imageId, edit, health, onResult }: Props) {
  const [consent, setConsent] = useState(false);
  const [fallback, setFallback] = useState(true);
  const [job, setJob] = useState<JobInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const timer = useRef<number>();
  const stopped = useRef(false);
  const startedFor = useRef("");

  useEffect(() => { stopped.current = false; return () => { stopped.current = true; window.clearTimeout(timer.current); }; }, []);
  useEffect(() => { setJob(null); setErr(null); window.clearTimeout(timer.current); }, [imageId]);

  const configured = !!health?.ai_provider.configured;

  function poll(id: string) {
    timer.current = window.setTimeout(async () => {
      if (stopped.current) return;
      try {
        const j = await getJob(id);
        setJob(j);
        if (j.status === "succeeded") {
          const url = await jobResultUrl(id);
          onResult({ url, modeUsed: j.mode_used ?? "ai", warning: j.warning, key: startedFor.current });
        } else if (j.status !== "failed") poll(id);
      } catch (e) { setErr(e instanceof Error ? e.message : "Lost contact with the server."); }
    }, 1000);
  }

  async function start(retry = false) {
    setErr(null); onResult(null);
    startedFor.current = JSON.stringify(edit);
    try {
      const j = retry && job ? await retryJob(job.job_id) : await createJob(imageId, edit, { mode: "ai", fallback_to_local: fallback, ai_consent: consent });
      setJob(j); poll(j.job_id);
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not start the AI job."); }
  }

  const running = job?.status === "queued" || job?.status === "running";
  return (
    <section className="rounded-2xl bg-panel p-5" aria-label="AI enhancement">
      <h2 className="text-lg font-semibold">AI enhancement</h2>
      {!health ? <p className="mt-2 text-sm text-dim">Checking server…</p> : !configured ? (
        <p className="mt-2 text-sm text-dim">Not available. No AI provider is configured on this server, so all editing runs locally and your photo never leaves it.</p>
      ) : (
        <>
          <p className="mt-2 text-sm text-dim">Uses {health.ai_provider.name} for an AI-edited version in your chosen style. Result is generated at up to 1536 px.</p>
          <label className="mt-3 flex items-start gap-2 text-sm">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-1 accent-[#d9a441]" />
            <span>I agree to send a downsized copy of this photo to {health.ai_provider.name}, a third-party service, for this edit.</span>
          </label>
          <label className="mt-2 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={fallback} onChange={(e) => setFallback(e.target.checked)} className="accent-[#d9a441]" />
            If AI fails, show the local result instead
          </label>
          <button onClick={() => start()} disabled={!consent || running} className="mt-3 w-full rounded-xl bg-gold px-4 py-2.5 font-semibold text-ink hover:brightness-110 disabled:opacity-50">
            {running ? "Working…" : "Generate AI version"}
          </button>
        </>
      )}
      <div aria-live="polite" className="mt-3 text-sm">
        {job && running && <p className="text-gold">{job.stage}</p>}
        {job?.status === "succeeded" && <p className="text-leaf">{job.mode_used === "ai" ? "AI result ready." : "Local result ready."}{job.warning && <span className="block text-gold">{job.warning}</span>}</p>}
        {job?.status === "failed" && (
          <p className="text-alert">{job.error} {job.retryable && <button onClick={() => start(true)} className="ml-1 underline">Retry</button>}</p>
        )}
        {err && <p role="alert" className="text-alert">{err}</p>}
      </div>
    </section>
  );
}
