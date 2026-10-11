import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

export function LoginPage() {
  const { login } = useAuth();
  const [userId, setUserId] = useState("");
  const [consoleSecret, setConsoleSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const uid = userId.trim();
    if (!uid || !consoleSecret) {
      setError("ต้องมี user id และ console secret จาก rbac.yaml");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.healthz();
      const me = await api.login(uid, consoleSecret);
      login({
        userId: String(me.user_id),
        userName: me.name,
        roles: me.roles || [],
        csrf: me.csrf,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login card">
      <h1>Operator Console</h1>
      <p className="sub">
        Login ด้วย Telegram user id + <code>console_secret</code> จาก rbac.yaml (ไม่ใช้ Hermes
        API key)
      </p>
      <form onSubmit={(e) => void onSubmit(e)}>
        <label htmlFor="uid">User id</label>
        <input
          id="uid"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          placeholder="987654321"
          autoComplete="username"
        />
        <label htmlFor="secret">Console secret</label>
        <input
          id="secret"
          type="password"
          autoComplete="current-password"
          value={consoleSecret}
          onChange={(e) => setConsoleSecret(e.target.value)}
        />
        <div className="row" style={{ marginTop: "1rem" }}>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "Signing in…" : "Login"}
          </button>
        </div>
        {error && <p className="err">{error}</p>}
      </form>
    </div>
  );
}
