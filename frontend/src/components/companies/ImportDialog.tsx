"use client";
import { useState } from "react";
import { upload } from "@/lib/api";
import type { ImportResult } from "@/types";
import { Badge } from "@/components/ui/StatusBadge";

export default function ImportDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<number | null>(null);

  const kind = file?.name.toLowerCase().endsWith(".xlsx") ? "excel" : "csv";

  async function run(mode: "preview" | "commit") {
    if (!file) return;
    setBusy(true); setError(null);
    try {
      const res = await upload<ImportResult>(`/imports/${kind}?mode=${mode}`, file);
      if (mode === "preview") setPreview(res);
      else { setCreated(res.created_company_ids.length); onDone(); }
    } catch (e) { setError(e instanceof Error ? e.message : "Import failed"); }
    finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-20 flex items-start justify-center overflow-auto bg-black/30 p-8">
      <div className="w-full max-w-3xl border border-gray-200 bg-white p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">Import companies</h2>
          <button className="btn" onClick={onClose}>Close</button>
        </div>
        {created !== null ? (
          <div className="space-y-3">
            <p className="text-sm text-green-700">Imported {created} {created === 1 ? "company" : "companies"}.</p>
            <button className="btn btn-primary" onClick={onClose}>Done</button>
          </div>
        ) : (
          <>
            <p className="mb-2 text-xs text-gray-500">
              CSV or Excel (.xlsx). Required columns: <code>company_name</code>, <code>website</code>. Optional:{" "}
              <code>linkedin_url</code>, <code>instagram_url</code>, <code>youtube_url</code>, <code>facebook_url</code>, <code>x_url</code>, <code>industry</code>.
            </p>
            <input type="file" accept=".csv,.xlsx" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPreview(null); setError(null); }} className="text-sm" />
            <div className="mt-3 flex gap-2">
              <button className="btn" disabled={!file || busy} onClick={() => run("preview")}>{busy && !preview ? "Reading..." : "Preview"}</button>
              {preview && (
                <button className="btn btn-primary" disabled={busy || preview.summary.valid === 0} onClick={() => run("commit")}>
                  Import {preview.summary.valid} valid {preview.summary.valid === 1 ? "row" : "rows"}
                </button>
              )}
            </div>
            {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
            {preview && (
              <div className="mt-4">
                <p className="mb-2 text-sm">
                  {preview.summary.total} rows: <b>{preview.summary.valid}</b> valid, <b>{preview.summary.duplicates}</b> duplicates, <b>{preview.summary.invalid}</b> invalid. Duplicates and invalid rows are skipped.
                </p>
                <div className="max-h-80 overflow-auto border border-gray-200">
                  <table className="w-full">
                    <thead className="sticky top-0 bg-white"><tr><th className="th">Row</th><th className="th">Company</th><th className="th">Domain</th><th className="th">Status</th><th className="th">Notes</th></tr></thead>
                    <tbody>
                      {preview.rows.map((r) => (
                        <tr key={r.row}>
                          <td className="td">{r.row}</td><td className="td">{r.data.company_name || "-"}</td>
                          <td className="td">{r.normalized_domain ?? r.data.website ?? "-"}</td>
                          <td className="td"><Badge value={r.status === "valid" ? "completed" : r.status === "duplicate" ? "partial" : "failed"} text={r.status} /></td>
                          <td className="td text-xs text-gray-600">{r.errors.join("; ")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
