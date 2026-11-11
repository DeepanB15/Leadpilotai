"use client";
import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";
import { supabase } from "@/lib/supabase";

export default function SettingsPage() {
  const [email, setEmail] = useState("");
  const [health, setHealth] = useState("checking...");
  useEffect(() => {
    void supabase().auth.getUser().then(({ data }) => setEmail(data.user?.email ?? ""));
    fetch(`${API_URL}/api/v1/health`).then((r) => r.json()).then((j) => setHealth(`${j.status} (database: ${j.database})`)).catch(() => setHealth("unreachable"));
  }, []);
  return (
    <div className="max-w-lg">
      <h1 className="mb-4 text-lg font-semibold">Settings</h1>
      <dl className="divide-y divide-gray-100 border-y border-gray-200 text-sm">
        <div className="flex justify-between py-2"><dt className="text-gray-500">Account</dt><dd>{email || "-"}</dd></div>
        <div className="flex justify-between py-2"><dt className="text-gray-500">API</dt><dd>{API_URL}</dd></div>
        <div className="flex justify-between py-2"><dt className="text-gray-500">API health</dt><dd>{health}</dd></div>
      </dl>
    </div>
  );
}
