"use client";

import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useApi } from "@/lib/useApi";
import type { EmployeeDetail, TimelineEntry } from "@/lib/types";
import { hms, timeOfDay } from "@/lib/format";
import { Badge, Card, PageHeader, Ring, SkeletonRows, Empty } from "@/components/ui";
import p from "../../pages.module.css";

const KIND_ICON: Record<string, string> = { shift: "◐", application: "▣", website: "◇" };

export default function EmployeeDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params?.id as string;

  const detail = useApi<EmployeeDetail>(id ? `/analytics/employees/${id}/detail` : null);
  const timeline = useApi<TimelineEntry[]>(id ? `/analytics/employees/${id}/timeline` : null);

  const d = detail.data;
  const prod = d?.productivity;
  const total = prod ? Math.max(1, prod.tracked_seconds) : 1;
  const segs = prod
    ? [
        { key: "Productive", val: prod.productive_seconds, color: "var(--ok)" },
        { key: "Neutral", val: prod.neutral_seconds, color: "var(--info)" },
        { key: "Unproductive", val: prod.unproductive_seconds, color: "var(--danger)" },
      ]
    : [];

  return (
    <>
      <PageHeader
        title="Employee detail"
        subtitle={`Today's attendance & productivity`}
        action={
          <button className={p.input} style={{ cursor: "pointer" }} onClick={() => router.back()}>
            ← Back
          </button>
        }
      />

      {detail.error && <div className={p.errBanner}>{detail.error}</div>}

      <div className={p.split}>
        <div className={p.grid}>
          <Card>
            <div className={p.sectionTitle}>Productivity</div>
            {detail.loading ? (
              <SkeletonRows rows={3} />
            ) : (
              <div style={{ display: "flex", gap: 26, alignItems: "center", flexWrap: "wrap" }}>
                <Ring value={prod?.indicator ?? 0} />
                <div style={{ flex: 1, minWidth: 220 }}>
                  <div className={p.mix}>
                    {segs.map((s) => (
                      <motion.div
                        key={s.key}
                        className={p.mixSeg}
                        style={{ background: s.color }}
                        initial={{ width: 0 }}
                        animate={{ width: `${(s.val / total) * 100}%` }}
                        transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
                      />
                    ))}
                  </div>
                  <div className={p.legend}>
                    {segs.map((s) => (
                      <span key={s.key} className={p.legendItem}>
                        <span className={p.legendDot} style={{ background: s.color }} />
                        {s.key} · {hms(s.val)}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </Card>

          <Card delay={0.05}>
            <div className={p.sectionTitle}>Attendance today</div>
            {detail.loading ? (
              <SkeletonRows rows={2} />
            ) : (
              <div className={p.statsGrid} style={{ margin: 0 }}>
                <Metric label="Status" node={<Badge label={d?.attendance.status || "—"} />} />
                <Metric label="Worked" node={<b>{hms(d?.attendance.worked_seconds)}</b>} />
                <Metric label="Break" node={<b>{hms(d?.attendance.break_seconds)}</b>} />
                <Metric label="Idle" node={<b>{hms(d?.attendance.idle_seconds)}</b>} />
                <Metric label="Late" node={<b>{hms(d?.attendance.late_seconds)}</b>} />
                <Metric label="Overtime" node={<b>{hms(d?.attendance.overtime_seconds)}</b>} />
              </div>
            )}
          </Card>
        </div>

        <Card delay={0.1}>
          <div className={p.sectionTitle}>Timeline</div>
          {timeline.loading ? (
            <SkeletonRows rows={6} />
          ) : !timeline.data || timeline.data.length === 0 ? (
            <Empty title="No activity yet" hint="Timeline populates as the agent reports." />
          ) : (
            <div>
              {timeline.data.map((t, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: 8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: Math.min(i * 0.03, 0.5) }}
                  style={tlRow}
                >
                  <span style={tlTime} className={p.mono}>
                    {timeOfDay(t.at)}
                  </span>
                  <span style={tlIcon}>{KIND_ICON[t.kind] || "•"}</span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 13.5 }}>{t.label}</div>
                    {t.detail && <div className={p.nameSub}>{t.detail}</div>}
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}

function Metric({ label, node }: { label: string; node: React.ReactNode }) {
  return (
    <div style={{ padding: "12px 14px", borderRadius: 12, background: "var(--surface)", border: "1px solid var(--border)" }}>
      <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: 15 }}>{node}</div>
    </div>
  );
}

const tlRow: React.CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  gap: 12,
  padding: "10px 0",
  borderBottom: "1px solid var(--border)",
};
const tlTime: React.CSSProperties = { width: 56, color: "var(--text-faint)", fontSize: 12.5, flexShrink: 0, paddingTop: 1 };
const tlIcon: React.CSSProperties = { width: 20, textAlign: "center", color: "var(--accent)" };
