import * as React from "react";
import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export function LoginPanel({ onLogin }: { onLogin: (ok: boolean) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/admin/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        setError("Invalid credentials");
        return;
      }
      const basic = btoa(`${username}:${password}`);
      sessionStorage.setItem("admin_basic", basic);
      onLogin(true);
    } catch (err) {
      setError("Login failed");
    }
  }

  return (
    <div className="max-w-md mx-auto bg-white p-6 rounded shadow">
      <h2 className="text-lg font-semibold mb-4">Admin login</h2>
      <form onSubmit={submit} className="space-y-3">
        <div>
          <label className="block text-xs font-medium">Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} className="w-full border px-2 py-1" />
        </div>
        <div>
          <label className="block text-xs font-medium">Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full border px-2 py-1" />
        </div>
        {error && <div className="text-sm text-red-600">{error}</div>}
        <div>
          <button className="px-4 py-2 bg-amber text-white rounded">Sign in</button>
        </div>
      </form>
    </div>
  );
}

export default LoginPanel;
