"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import type { AlertRow } from "@/lib/types";
import { shortDate } from "@/lib/format";
import { Badge, Card, PageHeader, SkeletonRows, Empty } from "@/components/ui";
import p from "../pages.module.css";

export default function AlertsPage() {
  const [status, setStatus] = useState("open");
  const { data, loading, error, reload } = useApi<AlertRow[]>(`/alerts?status=${status}`, [status]);
  const [busy, setBusy] = useState<string | null>(null);

  async function act(id: string, action: "acknowledge" | "resolve") {
    setBusy(id);
    try {
      await api(`/alerts/${id}/${action}`, { method: "POST" });
      reload();
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader title="Alerts" subtitle="Late arrivals, idle, missed shifts and more." />

      {error && <div className={p.errBanner}>{error}</div>}

      <div className={p.filters}>
        {["open", "acknowledged", "resolved"].map((s) => (
          <button
            key={s}
            className={p.input}
            style={{
              cursor: "pointer",
              borderColor: status === s ? "var(--accent)" : "var(--border)",
              color: status === s ? "var(--text)" : "var(--text-dim)",
            }}
            onClick={() => setStatus(s)}
          >
            {s}
          </button>
        ))}
      </div>

      <Card>
        {loading ? (
          <SkeletonRows rows={6} />
        ) : !data || data.length === 0 ? (
          <Empty title="Nothing here" hint={`No ${status} alerts.`} />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {data.map((a, i) => (
              <motion.div
                key={a.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i * 0.03, 0.4) }}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 14,
                  padding: "13px 15px",
                  borderRadius: 14,
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <Badge label={a.severity} />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>{a.message}</div>
                    <div className={p.nameSub}>{shortDate(a.created_at)}</div>
                  </div>
                </div>
                {status !== "resolved" && (
                  <div style={{ display: "flex", gap: 8 }}>
                    {status === "open" && (
                      <button
                        className={p.input}
                        style={{ cursor: "pointer", fontSize: 12.5 }}
                        disabled={busy === a.id}
                        onClick={() => act(a.id, "acknowledge")}
                      >
                        Ack
                      </button>
                    )}
                    <button
                      className={p.input}
                      style={{ cursor: "pointer", fontSize: 12.5, borderColor: "var(--ok)", color: "var(--ok)" }}
                      disabled={busy === a.id}
                      onClick={() => act(a.id, "resolve")}
                    >
                      Resolve
                    </button>
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        )}
      </Card>
    </>
  );
}
