"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, download } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { fmtDate, isActive, PLATFORM_LABEL } from "@/lib/utils";
import type { Company, Page } from "@/types";
import { Badge } from "@/components/ui/StatusBadge";
import ImportDialog from "./ImportDialog";

const PAGE = 25;
const FILTERS = ["", "completed", "partial", "failed", "queued", "researching", "pending"];

function socials(c: Company): string {
  return c.platforms.length ? c.platforms.map((p) => PLATFORM_LABEL[p] ?? p).join(", ") : "-";
}

export default function CompaniesPanel({ limit = PAGE, onChange }: { limit?: number; onChange?: () => void }) {
  const [data, setData] = useState<Page<Company> | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [showImport, setShowImport] = useState(false);

  const load = useCallback(async () => {
    try {
      const p = new URLSearchParams({ limit: String(limit), offset: String(offset) });
      if (q.trim()) p.set("q", q.trim());
      if (status) p.set("status", status);
      setData(await api<Page<Company>>(`/companies?${p}`));
      setError(null);
      onChange?.();
    } catch (e) { setError(e instanceof Error ? e.message : "Failed to load companies"); }
  }, [q, status, offset, limit, onChange]);

  useEffect(() => { const t = setTimeout(() => void load(), 200); return () => clearTimeout(t); }, [load]);
  usePolling(load, 5000, !!data?.items.some((c) => isActive(c.latest_status)));

  const toggle = (id: string) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  async function research(ids: string[]) {
    setNote(null);
    try {
      const res = await api<{ jobs: { company_id: string; error?: string }[] }>("/research/batch", { method: "POST", json: { company_ids: ids } });
      const failed = res.jobs.filter((j) => j.error);
      setNote(`Started ${res.jobs.length - failed.length} research job(s)${failed.length ? `; ${failed.length} skipped (already running)` : ""}.`);
      setSelected(new Set());
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start research"); }
  }

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input className="input max-w-[220px]" placeholder="Search name or domain" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} />
        <select className="input max-w-[160px]" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
          {FILTERS.map((f) => <option key={f} value={f}>{f ? f.replace(/_/g, " ") : "All statuses"}</option>)}
        </select>
        <div className="ml-auto flex gap-2">
          <button className="btn" disabled={selected.size === 0} onClick={() => research([...selected])}>Research selected ({selected.size})</button>
          <button className="btn" onClick={() => setShowImport(true)}>Import CSV / Excel</button>
          <button className="btn" onClick={() => download("/companies/export/csv", "companies.csv").catch((e) => setError(String(e.message ?? e)))}>Export CSV</button>
          <Link href="/companies/new" className="btn btn-primary">Add company</Link>
        </div>
      </div>
      {error && <p className="mb-2 text-sm text-red-600">{error}</p>}
      {note && <p className="mb-2 text-sm text-green-700">{note}</p>}
      <table className="w-full">
        <thead>
          <tr>
            <th className="th w-8"><input type="checkbox" aria-label="Select all" checked={items.length > 0 && items.every((c) => selected.has(c.id))}
              onChange={(e) => setSelected(e.target.checked ? new Set(items.map((c) => c.id)) : new Set())} /></th>
            <th className="th">Company</th><th className="th">Status</th><th className="th">Social profiles</th><th className="th">Last researched</th><th className="th" />
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.id} className="hover:bg-gray-50">
              <td className="td"><input type="checkbox" aria-label={`Select ${c.name}`} checked={selected.has(c.id)} onChange={() => toggle(c.id)} /></td>
              <td className="td"><Link href={`/companies/${c.id}`} className="font-medium hover:underline">{c.name}</Link><div className="text-xs text-gray-500">{c.normalized_domain}</div></td>
              <td className="td"><Badge value={c.latest_status} /></td>
              <td className="td text-xs text-gray-600">{socials(c)}</td>
              <td className="td text-xs text-gray-600">{fmtDate(c.last_researched_at)}</td>
              <td className="td text-right"><button className="btn" disabled={isActive(c.latest_status)} onClick={() => research([c.id])}>Research</button></td>
            </tr>
          ))}
          {data && items.length === 0 && <tr><td className="td text-gray-500" colSpan={6}>No companies yet. Add one or import a CSV/Excel file.</td></tr>}
          {!data && !error && <tr><td className="td text-gray-500" colSpan={6}>Loading...</td></tr>}
        </tbody>
      </table>
      {total > limit && (
        <div className="mt-3 flex items-center gap-2 text-sm text-gray-600">
          <button className="btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>Previous</button>
          <span>{offset + 1}-{Math.min(offset + limit, total)} of {total}</span>
          <button className="btn" disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}>Next</button>
        </div>
      )}
      {showImport && <ImportDialog onClose={() => setShowImport(false)} onDone={() => void load()} />}
    </div>
  );
}
