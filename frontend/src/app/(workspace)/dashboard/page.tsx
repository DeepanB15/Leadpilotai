"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Stats } from "@/types";
import CompaniesPanel from "@/components/companies/CompaniesPanel";

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const loadStats = useCallback(async () => {
    try { setStats(await api<Stats>("/dashboard/stats")); } catch { /* shown by panel */ }
  }, []);
  useEffect(() => { void loadStats(); }, [loadStats]);

  const tiles: [string, number | undefined][] = [
    ["Total companies", stats?.total], ["Completed", stats?.completed], ["Processing", stats?.processing],
    ["Failed or partial", stats?.failed_or_partial],
  ];
  return (
    <div>
      <h1 className="text-lg font-semibold">Company research</h1>
      <p className="mb-4 text-sm text-gray-500">Manage and understand your prospective businesses.</p>
      <div className="mb-6 grid max-w-3xl grid-cols-4 gap-4 border-b border-gray-200 pb-4">
        {tiles.map(([t, n]) => (
          <div key={t}><div className="text-xs text-gray-500">{t}</div><div className="text-2xl font-semibold">{n ?? "-"}</div></div>
        ))}
      </div>
      <CompaniesPanel limit={10} onChange={loadStats} />
    </div>
  );
}
