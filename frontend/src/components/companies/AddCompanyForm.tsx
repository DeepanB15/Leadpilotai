"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Company } from "@/types";

const SOCIAL = [
  ["linkedin_url", "LinkedIn", "linkedin.com/company/acme"],
  ["instagram_url", "Instagram", "instagram.com/acme"],
  ["youtube_url", "YouTube", "youtube.com/@acme"],
  ["facebook_url", "Facebook", "facebook.com/acme"],
  ["x_url", "X", "x.com/acme"],
] as const;

export default function AddCompanyForm() {
  const router = useRouter();
  const [form, setForm] = useState<Record<string, string>>({ name: "", website_url: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    const body: Record<string, string | null> = {};
    for (const [k, v] of Object.entries(form)) body[k] = v.trim() || null;
    try {
      const c = await api<Company>("/companies", { method: "POST", json: body });
      router.push(`/companies/${c.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.code === "duplicate") {
        const id = (err.details as { existing_company_id?: string } | undefined)?.existing_company_id;
        setError(`${err.message}.`);
        if (id) setTimeout(() => router.push(`/companies/${id}`), 1200);
      } else setError(err instanceof Error ? err.message : "Failed to create company");
    } finally { setBusy(false); }
  }

  return (
    <form onSubmit={submit} className="max-w-lg space-y-3">
      <div>
        <label className="label" htmlFor="name">Company name</label>
        <input id="name" className="input" required value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Acme Software" />
      </div>
      <div>
        <label className="label" htmlFor="site">Website URL</label>
        <input id="site" className="input" required value={form.website_url} onChange={(e) => set("website_url", e.target.value)} placeholder="https://acme.com" />
      </div>
      <div>
        <div className="section-title mt-4">Social profile URLs (optional)</div>
        <div className="grid grid-cols-2 gap-2">
          {SOCIAL.map(([k, name, ph]) => (
            <div key={k}>
              <label className="label" htmlFor={k}>{name}</label>
              <input id={k} className="input" value={form[k] ?? ""} onChange={(e) => set(k, e.target.value)} placeholder={ph} />
            </div>
          ))}
        </div>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex gap-2 pt-1">
        <button className="btn btn-primary" disabled={busy}>{busy ? "Saving..." : "Add company"}</button>
        <button type="button" className="btn" onClick={() => router.back()}>Cancel</button>
      </div>
    </form>
  );
}
