"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { useApi } from "@/lib/useApi";
import type { AttendanceRow } from "@/lib/types";
import { hms, shortDate } from "@/lib/format";
import { Badge, Card, PageHeader, SkeletonRows, Empty } from "@/components/ui";
import p from "../pages.module.css";

export default function AttendancePage() {
  const [status, setStatus] = useState("");
  const path = status ? `/attendance?status=${status}` : "/attendance";
  const { data, loading, error } = useApi<AttendanceRow[]>(path, [status]);

  const STATUSES = ["", "PRESENT", "LATE", "ABSENT", "OVERTIME", "EARLY_LEAVE", "MISSED_SHIFT"];

  return (
    <>
      <PageHeader title="Attendance" subtitle="Derived from authoritative shift events." />

      {error && <div className={p.errBanner}>{error}</div>}

      <div className={p.filters}>
        {STATUSES.map((s) => (
          <button
            key={s || "all"}
            className={p.input}
            style={{
              cursor: "pointer",
              borderColor: status === s ? "var(--accent)" : "var(--border)",
              color: status === s ? "var(--text)" : "var(--text-dim)",
            }}
            onClick={() => setStatus(s)}
          >
            {s ? s.replace(/_/g, " ").toLowerCase() : "all"}
          </button>
        ))}
      </div>

      <Card>
        {loading ? (
          <SkeletonRows rows={8} />
        ) : !data || data.length === 0 ? (
          <Empty title="No attendance records" hint="Records appear as shifts complete." />
        ) : (
          <table className={p.table}>
            <thead>
              <tr>
                <th>Date</th>
                <th>Status</th>
                <th>Worked</th>
                <th>Break</th>
                <th>Late</th>
                <th>Overtime</th>
              </tr>
            </thead>
            <tbody>
              {data.map((r, i) => (
                <motion.tr
                  key={r.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: Math.min(i * 0.025, 0.4) }}
                >
                  <td className={p.mono}>{shortDate(r.work_date)}</td>
                  <td>
                    <Badge label={r.status} />
                  </td>
                  <td className={p.mono}>{hms(r.worked_seconds)}</td>
                  <td className={p.mono}>{hms(r.break_seconds)}</td>
                  <td className={p.mono}>{hms(r.late_seconds)}</td>
                  <td className={p.mono}>{hms(r.overtime_seconds)}</td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
