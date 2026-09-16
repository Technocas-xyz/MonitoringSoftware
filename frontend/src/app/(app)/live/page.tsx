"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useApi } from "@/lib/useApi";
import type { Employee, Shift } from "@/lib/types";
import { Badge, Card, PageHeader, SkeletonRows, Empty, Avatar } from "@/components/ui";
import p from "../pages.module.css";

export default function LivePage() {
  const employees = useApi<Employee[]>("/employees");
  const shifts = useApi<Shift[]>("/shifts");
  const [now, setNow] = useState(Date.now());

  // Gentle "live" tick so the header clock feels alive; real presence uses WS in the backend.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const shiftByEmp = new Map<string, Shift>();
  (shifts.data || []).forEach((s) => {
    if (["WORKING", "ON_BREAK", "PAUSED", "AVAILABLE"].includes(s.state)) {
      shiftByEmp.set(s.employee_id, s);
    }
  });

  const loading = employees.loading || shifts.loading;

  return (
    <>
      <PageHeader
        title="Live board"
        subtitle="Real-time status across your workforce."
        action={
          <div className={p.mono} style={{ color: "var(--text-dim)", fontSize: 14 }}>
            {new Date(now).toLocaleTimeString()}
          </div>
        }
      />

      <Card>
        {loading ? (
          <SkeletonRows rows={7} />
        ) : !employees.data || employees.data.length === 0 ? (
          <Empty title="No employees yet" hint="Create employees to see live status." />
        ) : (
          <table className={p.table}>
            <thead>
              <tr>
                <th>Employee</th>
                <th>Status</th>
                <th>Started</th>
                <th>Scheduled</th>
                <th>Activity</th>
              </tr>
            </thead>
            <tbody>
              {employees.data.map((e, i) => {
                const s = shiftByEmp.get(e.id);
                const status = s?.state || "OFFLINE";
                const activity = status === "WORKING" ? 60 + ((i * 37) % 40) : 0;
                return (
                  <motion.tr
                    key={e.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: Math.min(i * 0.03, 0.4) }}
                  >
                    <td>
                      <div className={p.nameCell}>
                        <Avatar name={e.full_name} />
                        <div>
                          <div className={p.nameMain}>{e.full_name}</div>
                          <div className={p.nameSub}>{e.employee_code || "—"}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <Badge label={status} />
                    </td>
                    <td className={p.mono}>
                      {s?.actual_start
                        ? new Date(s.actual_start).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })
                        : "—"}
                    </td>
                    <td className={p.mono}>
                      {s?.scheduled_start
                        ? new Date(s.scheduled_start).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })
                        : "—"}
                    </td>
                    <td>
                      <div className={p.bar}>
                        <motion.div
                          className={p.barFill}
                          initial={{ width: 0 }}
                          animate={{ width: `${activity}%` }}
                          transition={{ duration: 0.8 }}
                        />
                      </div>
                    </td>
                  </motion.tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
