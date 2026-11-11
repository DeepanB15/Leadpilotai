"use client";
import { useState } from "react";
import { fmtDate, label, PLATFORM_LABEL, cx } from "@/lib/utils";
import type { Coverage, Finding, Report, Source, SourceList } from "@/types";
import { Badge } from "@/components/ui/StatusBadge";

const TABS = ["Overview", "Website", "Social", "Insights", "Evidence", "Sales Prep"] as const;
type Tab = (typeof TABS)[number];

const Unknown = () => <span className="text-gray-400">unknown</span>;
const val = (v?: string) => (!v || v === "unknown" ? <Unknown /> : <>{v}</>);

export default function CompanyReport({ report, sources }: { report: Report; sources: SourceList | null }) {
  const [tab, setTab] = useState<Tab>("Overview");
  return (
    <div>
      <div className="mb-4 flex gap-1 border-b border-gray-200">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={cx("-mb-px border-b-2 px-3 py-1.5 text-sm", tab === t ? "border-gray-900 font-medium" : "border-transparent text-gray-500 hover:text-gray-800")}>
            {t}
          </button>
        ))}
      </div>
      {tab === "Overview" && <OverviewTab report={report} />}
      {tab === "Website" && <WebsiteTab sources={sources} />}
      {tab === "Social" && <SocialTab sources={sources} coverage={report.research_coverage} />}
      {tab === "Insights" && <InsightsTab findings={report.findings} />}
      {tab === "Evidence" && <EvidenceTab report={report} />}
      {tab === "Sales Prep" && <SalesTab report={report} />}
    </div>
  );
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[150px_1fr] border-b border-gray-100 py-2 text-sm">
      <dt className="text-gray-500">{k}</dt><dd>{children}</dd>
    </div>
  );
}

function OverviewTab({ report }: { report: Report }) {
  const o = report.overview;
  const list = (items?: { name: string; description: string }[]) =>
    items && items.length ? (
      <ul className="space-y-1">{items.map((i) => <li key={i.name}><b>{i.name}</b>{i.description ? ` - ${i.description}` : ""}</li>)}</ul>
    ) : <Unknown />;
  return (
    <div className="max-w-4xl space-y-6">
      {report.analysis.status !== "completed" && (
        <p className="border border-amber-200 bg-amber-50 p-2 text-sm text-amber-800">
          AI analysis is unavailable for this report{report.analysis.error ? `: ${report.analysis.error}` : "."} Source coverage below is still accurate.
        </p>
      )}
      <section>
        <div className="section-title">Company overview</div>
        <dl>
          <Row k="Description">{val(o.description)}</Row>
          <Row k="Industry">{val(o.industry ?? undefined)}</Row>
          <Row k="Business model">{val(o.business_model)}</Row>
          <Row k="Target audience">{o.target_audience?.length ? o.target_audience.join(", ") : <Unknown />}</Row>
          <Row k="Products">{list(o.products)}</Row>
          <Row k="Services">{list(o.services)}</Row>
          <Row k="Positioning">{val(o.market_positioning)}</Row>
          <Row k="Website presence">{val(o.digital_presence?.website)}</Row>
          <Row k="Social presence">{val(o.digital_presence?.social)}</Row>
          <Row k="Content themes">{o.content_themes?.length ? o.content_themes.join("; ") : <Unknown />}</Row>
        </dl>
      </section>
      <section>
        <div className="section-title">Research coverage</div>
        <CoverageTable coverage={report.research_coverage} />
      </section>
      {report.limitations.length > 0 && (
        <section>
          <div className="section-title">Limitations</div>
          <ul className="list-disc space-y-1 pl-5 text-sm text-gray-700">{report.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        </section>
      )}
      <p className="text-xs text-gray-500">
        Generated {fmtDate(report.generated_at)} · model {report.model_id ?? "n/a"} · prompt v{report.prompt_version} · pipeline v{report.pipeline_version}
      </p>
    </div>
  );
}

function CoverageTable({ coverage }: { coverage: Coverage[] }) {
  return (
    <table className="w-full">
      <thead><tr><th className="th">Source</th><th className="th">Status</th><th className="th">Verification</th><th className="th">Documents</th><th className="th">Last checked</th></tr></thead>
      <tbody>
        {coverage.map((c) => (
          <tr key={c.platform}>
            <td className="td">{PLATFORM_LABEL[c.platform] ?? c.platform}</td>
            <td className="td"><Badge value={c.status} /></td>
            <td className="td">{c.verification_status ? <Badge value={c.verification_status} /> : "-"}</td>
            <td className="td">{c.documents}</td>
            <td className="td text-xs text-gray-600">{fmtDate(c.last_checked_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Docs({ source }: { source: Source }) {
  const [open, setOpen] = useState<string | null>(null);
  const docs = source.documents ?? [];
  if (!docs.length) return <p className="text-xs text-gray-500">No documents collected.</p>;
  return (
    <ul className="divide-y divide-gray-100 border-y border-gray-100">
      {docs.map((d) => (
        <li key={d.id} className="py-2">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-sm font-medium">{d.title || label(d.document_type)}</div>
              <a href={d.url} target="_blank" rel="noopener noreferrer" className="block truncate text-xs text-blue-700 hover:underline">{d.url}</a>
              <div className="text-xs text-gray-500">{label(d.document_type)} · collected {fmtDate(d.collected_at)}{d.published_at ? ` · published ${fmtDate(d.published_at)}` : ""}</div>
            </div>
            <button className="btn shrink-0" onClick={() => setOpen(open === d.id ? null : d.id)}>{open === d.id ? "Hide" : "View text"}</button>
          </div>
          {open === d.id && <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap border border-gray-200 bg-gray-50 p-2 text-xs">{d.content}</pre>}
        </li>
      ))}
    </ul>
  );
}

function WebsiteTab({ sources }: { sources: SourceList | null }) {
  const web = sources?.items.find((s) => s.platform === "website");
  if (!web) return <p className="text-sm text-gray-500">No website research has been recorded.</p>;
  const errs = (web.profile_metadata?.page_errors as { url: string; error: string }[] | undefined) ?? [];
  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex items-center gap-2 text-sm"><Badge value={web.access_status} /><span>{web.source_url}</span><span className="text-xs text-gray-500">checked {fmtDate(web.last_checked_at)}</span></div>
      {web.status_detail && <p className="text-sm text-gray-600">{web.status_detail}</p>}
      <Docs source={web} />
      {errs.length > 0 && (
        <div>
          <div className="section-title">Pages not collected</div>
          <ul className="space-y-1 text-xs text-gray-600">{errs.map((e) => <li key={e.url}>{e.url} - {e.error}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

function SocialTab({ sources, coverage }: { sources: SourceList | null; coverage: Coverage[] }) {
  const platforms = ["linkedin", "instagram", "youtube", "facebook", "x"];
  return (
    <div className="max-w-4xl space-y-5">
      {platforms.map((p) => {
        const src = sources?.items.find((s) => s.platform === p);
        const cov = coverage.find((c) => c.platform === p);
        return (
          <section key={p} className="border-b border-gray-100 pb-4">
            <div className="mb-1 flex items-center gap-2">
              <h3 className="text-sm font-semibold">{PLATFORM_LABEL[p]}</h3>
              <Badge value={src?.access_status ?? cov?.status ?? "not_discovered"} />
              {src && <Badge value={src.verification_status} />}
            </div>
            {!src ? (
              <p className="text-xs text-gray-500">No {PLATFORM_LABEL[p]} profile was discovered or supplied. This does not mean the company has no presence there.</p>
            ) : (
              <>
                <a href={src.source_url} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-700 hover:underline">{src.source_url}</a>
                <p className="text-xs text-gray-500">Found via {label(src.discovery_method)} · checked {fmtDate(src.last_checked_at)}</p>
                {src.status_detail && <p className="mt-1 text-xs text-gray-700">{src.status_detail}</p>}
                {typeof src.profile_metadata?.verification_reason === "string" && <p className="text-xs text-gray-500">Verification: {src.profile_metadata.verification_reason}</p>}
                <div className="mt-2"><Docs source={src} /></div>
              </>
            )}
          </section>
        );
      })}
    </div>
  );
}

function EvidenceList({ f }: { f: Finding }) {
  if (!f.evidence.length) return <p className="mt-1 text-xs text-gray-500">No evidence (could not be verified).</p>;
  return (
    <ul className="mt-2 space-y-1">
      {f.evidence.map((e, i) => (
        <li key={i} className="border-l-2 border-gray-300 pl-2 text-xs text-gray-700">
          &ldquo;{e.excerpt}&rdquo; <a href={e.source_url} target="_blank" rel="noopener noreferrer" className="text-blue-700 hover:underline">source</a>
        </li>
      ))}
    </ul>
  );
}

function InsightsTab({ findings }: { findings: Finding[] }) {
  const [filter, setFilter] = useState("");
  const shown = findings.filter((f) => !filter || f.classification === filter);
  return (
    <div className="max-w-4xl">
      <div className="mb-3 flex items-center gap-2">
        <select className="input max-w-[200px]" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All classifications</option><option value="observed_fact">Observed fact</option>
          <option value="inference">Inference</option><option value="unknown">Unknown</option>
        </select>
        <span className="text-xs text-gray-500">{shown.length} finding(s)</span>
      </div>
      {shown.length === 0 && <p className="text-sm text-gray-500">No evidence-backed findings are available for this report.</p>}
      <ul className="space-y-4">
        {shown.map((f) => (
          <li key={f.id} className="border-b border-gray-100 pb-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium">{f.title}</span>
              <Badge value={f.classification} />
              <span title={JSON.stringify(f.confidence_factors.breakdown ?? {})}><Badge value={f.confidence} text={`confidence: ${f.confidence}`} /></span>
              <span className="text-xs text-gray-400">{label(f.finding_type)}</span>
            </div>
            <p className="mt-1 text-sm text-gray-700">{f.description}</p>
            <EvidenceList f={f} />
            {f.confidence_factors.breakdown && Object.keys(f.confidence_factors.breakdown).length > 0 && (
              <p className="mt-1 text-xs text-gray-500">
                Confidence points: {Object.entries(f.confidence_factors.breakdown).map(([k, v]) => `${label(k)} ${v > 0 ? "+" : ""}${v}`).join(", ")} = {f.confidence_factors.points}
                {f.confidence_factors.capped_for_inference ? " (capped at medium: inference)" : ""}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function EvidenceTab({ report }: { report: Report }) {
  return (
    <div className="max-w-4xl space-y-6">
      <section>
        <div className="section-title">Profile fields and their evidence</div>
        {report.profile.fields.length === 0 ? <p className="text-sm text-gray-500">No profile was generated.</p> : (
          <table className="w-full">
            <thead><tr><th className="th">Field</th><th className="th">Value</th><th className="th">Type</th><th className="th">Evidence</th></tr></thead>
            <tbody>
              {report.profile.fields.map((f, i) => (
                <tr key={i}>
                  <td className="td text-xs">{label(f.field.replace(".", " "))}</td>
                  <td className="td">{f.value === "unknown" ? <Unknown /> : f.value}{f.description ? <div className="text-xs text-gray-500">{f.description}</div> : null}</td>
                  <td className="td"><Badge value={f.classification} /></td>
                  <td className="td text-xs">
                    {f.evidence.map((e, j) => <div key={j} className="mb-1">&ldquo;{e.excerpt}&rdquo; <a className="text-blue-700 hover:underline" href={e.source_url} target="_blank" rel="noopener noreferrer">source</a></div>)}
                    {f.evidence.length === 0 && <span className="text-gray-400">none</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <section>
        <div className="section-title">Collected sources ({report.sources.length})</div>
        <table className="w-full">
          <thead><tr><th className="th">URL</th><th className="th">Source</th><th className="th">Type</th><th className="th">Collected</th></tr></thead>
          <tbody>
            {report.sources.map((s) => (
              <tr key={s.document_id}>
                <td className="td break-all text-xs"><a className="text-blue-700 hover:underline" href={s.url} target="_blank" rel="noopener noreferrer">{s.url}</a></td>
                <td className="td text-xs">{PLATFORM_LABEL[s.platform] ?? s.platform}</td>
                <td className="td text-xs">{label(s.document_type)}</td>
                <td className="td text-xs text-gray-600">{fmtDate(s.collected_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function SalesTab({ report }: { report: Report }) {
  const sp = report.sales_preparation;
  const titleOf = (id: string) => report.findings.find((f) => f.id === id)?.title ?? "finding";
  const Item = ({ it }: { it: { text: string; based_on_findings: string[] } }) => (
    <li className="mb-2">
      <div className="text-sm">{it.text}</div>
      <div className="text-xs text-gray-500">Based on: {it.based_on_findings.map(titleOf).join("; ")}</div>
    </li>
  );
  const empty = !sp.talking_points.length && !sp.prospect_questions.length && !sp.value_proposition && !sp.suggested_next_action;
  if (empty) return <p className="text-sm text-gray-500">No grounded sales preparation is available. It is generated only from validated findings.</p>;
  return (
    <div className="max-w-3xl space-y-5">
      {sp.talking_points.length > 0 && <section><div className="section-title">Talking points</div><ul className="list-disc pl-5">{sp.talking_points.map((t, i) => <Item key={i} it={t} />)}</ul></section>}
      {sp.prospect_questions.length > 0 && <section><div className="section-title">Questions to ask</div><ul className="list-disc pl-5">{sp.prospect_questions.map((t, i) => <Item key={i} it={t} />)}</ul></section>}
      {sp.value_proposition && <section><div className="section-title">Potential value proposition</div><ul><Item it={sp.value_proposition} /></ul></section>}
      {sp.suggested_next_action && <section><div className="section-title">Suggested next action</div><ul><Item it={sp.suggested_next_action} /></ul></section>}
    </div>
  );
}
