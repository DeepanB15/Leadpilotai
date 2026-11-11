import { cx, label } from "@/lib/utils";

const TONE: Record<string, string> = {
  completed: "bg-green-50 text-green-700 border-green-200",
  verified: "bg-green-50 text-green-700 border-green-200",
  high: "bg-green-50 text-green-700 border-green-200",
  observed_fact: "bg-green-50 text-green-700 border-green-200",
  partial: "bg-amber-50 text-amber-700 border-amber-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  inference: "bg-blue-50 text-blue-700 border-blue-200",
  unverified: "bg-amber-50 text-amber-700 border-amber-200",
  failed: "bg-red-50 text-red-700 border-red-200",
  rejected: "bg-red-50 text-red-700 border-red-200",
  inaccessible: "bg-red-50 text-red-700 border-red-200",
  low: "bg-red-50 text-red-700 border-red-200",
  unsupported: "bg-gray-100 text-gray-600 border-gray-300",
  not_discovered: "bg-gray-50 text-gray-500 border-gray-200",
  cancelled: "bg-gray-100 text-gray-600 border-gray-300",
  queued: "bg-gray-50 text-gray-600 border-gray-200",
  discovering: "bg-blue-50 text-blue-700 border-blue-200",
  researching: "bg-blue-50 text-blue-700 border-blue-200",
  analyzing: "bg-blue-50 text-blue-700 border-blue-200",
  generating_report: "bg-blue-50 text-blue-700 border-blue-200",
};

export function Badge({ value, text }: { value: string | null | undefined; text?: string }) {
  const tone = TONE[value ?? ""] ?? "bg-gray-50 text-gray-600 border-gray-200";
  return (
    <span className={cx("inline-block whitespace-nowrap rounded border px-1.5 py-0.5 text-xs", tone)}>
      {text ?? label(value)}
    </span>
  );
}
