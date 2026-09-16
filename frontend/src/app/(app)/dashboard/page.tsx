"use client";

import { motion } from "framer-motion";
import { useApi } from "@/lib/useApi";
import type { AlertRow, Overview } from "@/lib/types";
import { hms } from "@/lib/format";
import { Badge, Card, Counter, PageHeader, Ring, SkeletonRows, Stat, Empty } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import p from "../pages.module.css";

export default function DashboardPage() {
  const { me } = useAuth();
  const { data, loading, error } = useApi<Overview>("/analytics/overview");
  const alerts = useApi<AlertRow[]>("/alerts?status=open");

  const ov = data;

  return (
    <>
      <PageHeader
        title={`Good to see you${me ? "" : ""} 👋`}
        subtitle="Here's how your workforce is doing today."
      />

      {error && <div className={p.errBanner}>{error}</div>}

      <div className={p.statsGrid}>
        <Stat
          label="Employees"
          value={<Counter value={ov?.employees ?? 0} />}
          accent="var(--info)"
          delay={0.02}
        />
        <Stat
          label="Working now"
          value={<Counter value={ov?.working ?? 0} />}
          accent="var(--ok)"
          delay={0.06}
        />
        <Stat
          label="On break"
          value={<Counter value={ov?.on_break ?? 0} />}
          accent="var(--warn)"
          delay={0.1}
        />
        <Stat
          label="Not started"
          value={<Counter value={ov?.not_started ?? 0} />}
          accent="var(--text-faint)"
          delay={0.14}
        />
      </div>

      <div className={p.split}>
        <Card delay={0.18}>
          <div className={p.sectionTitle}>Workforce pulse</div>
          <div style={{ display: "flex", gap: 26, alignItems: "center", flexWrap: "wrap" }}>
            <Ring value={ov?.productivity_indicator ?? 0} />
            <div style={{ flex: 1, minWidth: 220 }}>
              <MetricRow
                label="Avg. worked today"
                value={hms(ov?.average_worked_seconds)}
                pct={Math.min(100, ((ov?.average_worked_seconds ?? 0) / (8 * 3600)) * 100)}
              />
              <MetricRow
                label="Currently working"
                value={`${ov?.working ?? 0} / ${ov?.employees ?? 0}`}
                pct={ov?.employees ? ((ov.working / ov.employees) * 100) : 0}
              />
              <MetricRow
                label="On break"
                value={`${ov?.on_break ?? 0}`}
                pct={ov?.employees ? ((ov.on_break / ov.employees) * 100) : 0}
                color="var(--warn)"
              />
            </div>
          </div>
        </Card>

        <Card delay={0.22}>
          <div className={p.sectionTitle}>
            Open alerts
            {alerts.data && alerts.data.length > 0 && (
              <span className={p.nameSub}>{alerts.data.length}</span>
            )}
          </div>
          {alerts.loading ? (
            <SkeletonRows rows={4} />
          ) : !alerts.data || alerts.data.length === 0 ? (
            <Empty title="All clear" hint="No open alerts right now." />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {alerts.data.slice(0, 6).map((a, i) => (
                <motion.div
                  key={a.id}
                  initial={{ opacity: 0, x: 10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.05 * i }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 12,
                    padding: "10px 12px",
                    borderRadius: 12,
                    background: "var(--surface)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <span style={{ fontSize: 13.5 }}>{a.message}</span>
                  <Badge label={a.severity} />
                </motion.div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {loading && (
        <div style={{ marginTop: 20 }}>
          <SkeletonRows rows={2} />
        </div>
      )}
    </>
  );
}

function MetricRow({
  label,
  value,
  pct,
  color = "var(--grad-primary)",
}: {
  label: string;
  value: string;
  pct: number;
  color?: string;
}) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 7 }}>
        <span className="muted" style={{ fontSize: 13 }}>
          {label}
        </span>
        <span style={{ fontSize: 13, fontWeight: 600 }}>{value}</span>
      </div>
      <div className={p.bar}>
        <motion.div
          className={p.barFill}
          style={{ background: color }}
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
          transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>
    </div>
  );
}
