import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

type UserOpt = { user_id: number; name: string; roles: string[] };

export function LoginPage() {
  const { login } = useAuth();
  const [apiKey, setApiKey] = useState("");
  const [users, setUsers] = useState<UserOpt[]>([]);
  const [userId, setUserId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loadingUsers, setLoadingUsers] = useState(false);

  async function loadUsers() {
    if (!apiKey.trim() || !userId.trim()) {
      setError("ใส่ API key และ user id (ที่มีสิทธิ์ status-report) เพื่อโหลดรายชื่อ");
      return;
    }
    setLoadingUsers(true);
    setError(null);
    try {
      await api.healthz();
      const data = await api.listUsers({
        apiKey: apiKey.trim(),
        userId: userId.trim(),
        userName: "tmp",
      });
      setUsers(data.users);
      if (data.users[0]) setUserId(String(data.users[0].user_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingUsers(false);
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const uid = userId.trim();
    if (!apiKey.trim() || !uid) {
      setError("ต้องมี API key และ user id");
      return;
    }
    const name = users.find((u) => String(u.user_id) === uid)?.name || `user-${uid}`;
    login(apiKey.trim(), uid, name);
  }

  return (
    <div className="login card">
      <h1>Operator Console</h1>
      <p className="sub">Bearer = HERMES_API_KEY · User = Telegram id จาก rbac.yaml</p>
      <form onSubmit={onSubmit}>
        <label htmlFor="key">API key</label>
        <input
          id="key"
          type="password"
          autoComplete="off"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
        />
        <label htmlFor="uid">User id</label>
        {users.length > 0 ? (
          <select id="uid" value={userId} onChange={(e) => setUserId(e.target.value)}>
            {users.map((u) => (
              <option key={u.user_id} value={u.user_id}>
                {u.name} ({u.user_id}) — {u.roles.join(",")}
              </option>
            ))}
          </select>
        ) : (
          <input
            id="uid"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="987654321"
          />
        )}
        <div className="row" style={{ marginTop: "1rem" }}>
          <button type="button" onClick={() => void loadUsers()} disabled={loadingUsers}>
            Load users
          </button>
          <button type="submit" className="primary">
            Login
          </button>
        </div>
        {error && <p className="err">{error}</p>}
      </form>
    </div>
  );
}
