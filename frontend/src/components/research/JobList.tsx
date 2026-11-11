"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { fmtDate, isActive, label, PLATFORM_LABEL } from "@/lib/utils";
import type { Job, JobStart, Page } from "@/types";
import { Badge } from "@/components/ui/StatusBadge";

export default function JobList() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, Job>>({});
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const page = await api<Page<Job>>("/research/jobs?limit=50");
      setJobs(page.items); setLoaded(true); setError(null);
    } catch (e) { setError(e instanceof Error ? e.message : "Failed to load jobs"); }
  }, []);
  const loadDetail = useCallback(async (id: string) => {
    try { const j = await api<Job>(`/research/jobs/${id}`); setDetail((d) => ({ ...d, [id]: j })); } catch { /* ignore */ }
  }, []);

  useEffect(() => { void load(); }, [load]);
  usePolling(async () => { await load(); if (open) await loadDetail(open); }, 3000, jobs.some((j) => isActive(j.status)) || !!open);

  async function act(id: string, action: "retry" | "cancel") {
    try { await api<JobStart | Job>(`/research/jobs/${id}/${action}`, { method: "POST" }); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : `Could not ${action} job`); }
  }

  return (
    <div>
      {error && <p className="mb-2 text-sm text-red-600">{error}</p>}
      <table className="w-full">
        <thead><tr><th className="th">Company</th><th className="th">Status</th><th className="th">Stage</th><th className="th">Started</th><th className="th">Finished</th><th className="th" /></tr></thead>
        <tbody>
          {jobs.map((j) => (
            <JobRow key={j.id} job={j} detail={detail[j.id]} open={open === j.id}
              onToggle={() => { const next = open === j.id ? null : j.id; setOpen(next); if (next) void loadDetail(j.id); }}
              onAct={(a) => act(j.id, a)} />
          ))}
          {loaded && jobs.length === 0 && <tr><td className="td text-gray-500" colSpan={6}>No research jobs yet. Start research from the Companies page.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function JobRow({ job: j, detail, open, onToggle, onAct }: { job: Job; detail?: Job; open: boolean; onToggle: () => void; onAct: (a: "retry" | "cancel") => void }) {
  const d = detail ?? j;
  return (
    <>
      <tr className="cursor-pointer hover:bg-gray-50" onClick={onToggle}>
        <td className="td"><Link href={`/companies/${j.company_id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>{j.company_name ?? j.company_id}</Link></td>
        <td className="td"><Badge value={j.status} /></td>
        <td className="td text-xs text-gray-600">{label(j.progress_stage)}</td>
        <td className="td text-xs text-gray-600">{fmtDate(j.started_at ?? j.created_at)}</td>
        <td className="td text-xs text-gray-600">{fmtDate(j.completed_at)}</td>
        <td className="td text-right" onClick={(e) => e.stopPropagation()}>
          {isActive(j.status) && <button className="btn" onClick={() => onAct("cancel")}>Cancel</button>}
          {["failed", "partial", "cancelled"].includes(j.status) && <button className="btn" onClick={() => onAct("retry")}>Retry</button>}
        </td>
      </tr>
      {open && (
        <tr><td className="td bg-gray-50" colSpan={6}>
          {d.error_info && <p className="mb-2 text-sm text-red-700">Error: {String(d.error_info.error ?? d.error_info.message ?? JSON.stringify(d.error_info))}</p>}
          {d.sources.length === 0 ? <p className="text-xs text-gray-500">No source results yet.</p> : (
            <table className="w-full"><thead><tr><th className="th">Source</th><th className="th">Access</th><th className="th">Verification</th><th className="th">Docs</th><th className="th">Detail</th></tr></thead>
              <tbody>{d.sources.map((s) => (
                <tr key={s.platform + (s.source_url ?? "")}>
                  <td className="td">{PLATFORM_LABEL[s.platform] ?? s.platform}</td><td className="td"><Badge value={s.access_status} /></td>
                  <td className="td">{s.verification_status ? <Badge value={s.verification_status} /> : "-"}</td><td className="td">{s.documents}</td>
                  <td className="td text-xs text-gray-600">{s.status_detail ?? ""}</td>
                </tr>))}</tbody></table>
          )}
          <p className="mt-2 text-xs text-gray-500">Attempt {d.attempt} · pipeline {d.pipeline_version ?? "-"}{d.model_id ? ` · model ${d.model_id}` : ""}</p>
        </td></tr>
      )}
    </>
  );
}
