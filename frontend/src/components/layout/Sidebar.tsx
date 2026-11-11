"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { cx } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/companies", label: "Companies" },
  { href: "/research", label: "Research" },
  { href: "/settings", label: "Settings" },
];

export default function Sidebar() {
  const path = usePathname();
  const router = useRouter();
  const [email, setEmail] = useState("");
  useEffect(() => { void supabase().auth.getUser().then(({ data }) => setEmail(data.user?.email ?? "")); }, []);

  async function signOut() {
    await supabase().auth.signOut();
    router.replace("/login");
  }

  return (
    <aside className="flex w-52 shrink-0 flex-col border-r border-gray-200 bg-gray-50/50">
      <div className="border-b border-gray-200 px-4 py-3 text-sm font-semibold">LeadPilotAI</div>
      <nav className="flex-1 py-2">
        {NAV.map((n) => (
          <Link key={n.href} href={n.href}
            className={cx("block px-4 py-1.5 text-sm text-gray-600 hover:bg-gray-100",
              path.startsWith(n.href) && "bg-gray-100 font-medium text-gray-900")}>
            {n.label}
          </Link>
        ))}
      </nav>
      <div className="border-t border-gray-200 p-3 text-xs text-gray-500">
        <div className="mb-2 truncate" title={email}>{email}</div>
        <button className="btn w-full justify-center" onClick={signOut}>Sign out</button>
      </div>
    </aside>
  );
}
