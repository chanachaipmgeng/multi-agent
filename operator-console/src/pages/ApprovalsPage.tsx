import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ApprovalRow } from "../api";
import { useAuth } from "../auth";

export function ApprovalsPage() {
  const { session } = useAuth();
  const [rows, setRows] = useState<ApprovalRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    if (!session) return;
    setError(null);
    try {
      const data = await api.listApprovals(session, "pending");
      setRows(data.approvals);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void load();
  }, [session]);

  async function decide(nonce: string, decision: "approved" | "rejected") {
    if (!session) return;
    setBusy(nonce);
    setError(null);
    try {
      await api.decideApproval(session, nonce, decision);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <h1>Approvals</h1>
      <p className="sub">HITL inbox (คู่ขนานกับ Telegram y/n)</p>
      <div className="row">
        <button type="button" className="primary" onClick={() => void load()}>
          Refresh
        </button>
      </div>
      {error && <p className="err">{error}</p>}
      {rows.map((r) => (
        <div className="card" key={r.nonce}>
          <div className="row">
            <span className="badge warn">{r.action}</span>
            <Link className="mono" to={`/tasks/${r.task_id}`}>
              {r.task_id}
            </Link>
            <span className="sub">role {r.required_role}</span>
            <span className="sub">timeout {r.timeout_at}</span>
          </div>
          <pre className="mono" style={{ whiteSpace: "pre-wrap" }}>
            {JSON.stringify(r.payload_summary || {}, null, 2)}
          </pre>
          <div className="row">
            <button
              type="button"
              className="primary"
              disabled={busy === r.nonce}
              onClick={() => void decide(r.nonce, "approved")}
            >
              Approve
            </button>
            <button
              type="button"
              className="danger"
              disabled={busy === r.nonce}
              onClick={() => void decide(r.nonce, "rejected")}
            >
              Reject
            </button>
          </div>
        </div>
      ))}
      {rows.length === 0 && <p className="sub">ไม่มี pending approval</p>}
    </>
  );
}
