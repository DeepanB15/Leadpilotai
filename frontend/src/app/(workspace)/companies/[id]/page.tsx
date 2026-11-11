"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError, download } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { fmtDate, isActive, label } from "@/lib/utils";
import type { Company, Job, JobStart, Page, Report, ReportSummary, SourceList } from "@/types";
import { Badge } from "@/components/ui/StatusBadge";
import CompanyReport from "@/components/reports/CompanyReport";

export default function CompanyPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [company, setCompany] = useState<Company | null>(null);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [reportId, setReportId] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [sources, setSources] = useState<SourceList | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const c = await api<Company>(`/companies/${id}`);
      setCompany(c);
      const [r, s, jobs] = await Promise.all([
        api<Page<ReportSummary>>(`/companies/${id}/reports`),
        api<SourceList>(`/companies/${id}/sources?include=documents`),
        api<Page<Job>>(`/research/jobs?company_id=${id}&limit=1`),
      ]);
      setReports(r.items); setSources(s); setJob(jobs.items[0] ?? null);
      setReportId((cur) => cur ?? r.items[0]?.id ?? null);
      setError(null);
    } catch (e) { setError(e instanceof Error ? e.message : "Failed to load company"); }
    finally { setLoaded(true); }
  }, [id]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!reportId) { setReport(null); return; }
    api<Report>(`/reports/${reportId}`).then(setReport).catch((e) => setError(e instanceof Error ? e.message : "Failed to load report"));
  }, [reportId]);

  const active = isActive(company?.latest_status);
  usePolling(async () => {
    await load();
    // switch to the newest report once the running job finishes
    const r = await api<Page<ReportSummary>>(`/companies/${id}/reports`).catch(() => null);
    if (r?.items[0]) setReportId(r.items[0].id);
  }, 3000, active);

  async function start() {
    setError(null);
    try { await api<JobStart>(`/companies/${id}/research`, { method: "POST" }); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not start research"); }
  }
  async function remove() {
    if (!company || !confirm(`Delete ${company.name} and all of its research? This cannot be undone.`)) return;
    try { await api(`/companies/${id}`, { method: "DELETE" }); router.replace("/companies"); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not delete"); }
  }

  if (!loaded) return <p className="text-sm text-gray-500">Loading...</p>;
  if (!company) return <p className="text-sm text-red-600">{error ?? "Company not found"} <Link href="/companies" className="underline">Back</Link></p>;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-gray-200 pb-3">
        <div>
          <Link href="/companies" className="text-xs text-gray-500 hover:underline">Companies</Link>
          <h1 className="text-lg font-semibold">{company.name}</h1>
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <a href={company.website_url} target="_blank" rel="noopener noreferrer" className="hover:underline">{company.normalized_domain}</a>
            <Badge value={company.latest_status} />
            {active && job && <span className="text-xs text-gray-500">{label(job.progress_stage)}...</span>}
            <span className="text-xs text-gray-500">Last researched {fmtDate(company.last_researched_at)}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {reports.length > 1 && (
            <select className="input w-auto" value={reportId ?? ""} onChange={(e) => setReportId(e.target.value)} aria-label="Report version">
              {reports.map((r) => <option key={r.id} value={r.id}>v{r.version} - {fmtDate(r.created_at)}</option>)}
            </select>
          )}
          <button className="btn btn-primary" disabled={active} onClick={start}>{reports.length ? "Re-run research" : "Start research"}</button>
          <button className="btn" disabled={!reportId} onClick={() => reportId && download(`/reports/${reportId}/export?format=pdf`, "report.pdf").catch((e) => setError(String(e.message ?? e)))}>Export PDF</button>
          <button className="btn" disabled={!reportId} onClick={() => reportId && download(`/reports/${reportId}/export?format=csv`, "report.csv").catch((e) => setError(String(e.message ?? e)))}>Export CSV</button>
          <button className="btn btn-danger" disabled={active} onClick={remove}>Delete</button>
        </div>
      </div>
      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}
      {job && ["failed", "partial"].includes(job.status) && job.error_info && (
        <p className="mb-3 border border-amber-200 bg-amber-50 p-2 text-sm text-amber-800">
          Latest run ended as {job.status}: {String(job.error_info.error ?? JSON.stringify(job.error_info))}
        </p>
      )}
      {report ? <CompanyReport report={report} sources={sources} /> : (
        <p className="text-sm text-gray-500">
          {active ? "Research is running. This page updates automatically." : "No research report yet. Start research to generate one."}
        </p>
      )}
    </div>
  );
}
