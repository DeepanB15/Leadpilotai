export const ACTIVE = ["queued", "discovering", "researching", "analyzing", "generating_report"];
export const isActive = (s: string | null | undefined) => !!s && ACTIVE.includes(s);

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function label(s: string | null | undefined): string {
  return s ? s.replace(/_/g, " ") : "not researched";
}

export const PLATFORM_LABEL: Record<string, string> = {
  website: "Website", linkedin: "LinkedIn", instagram: "Instagram", youtube: "YouTube", facebook: "Facebook", x: "X",
};

export function cx(...c: (string | false | null | undefined)[]): string {
  return c.filter(Boolean).join(" ");
}
