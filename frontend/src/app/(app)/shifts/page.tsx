"use client";

import { motion } from "framer-motion";
import { useApi } from "@/lib/useApi";
import type { Shift } from "@/lib/types";
import { timeOfDay } from "@/lib/format";
import { Badge, Card, PageHeader, SkeletonRows, Empty } from "@/components/ui";
import p from "../pages.module.css";

export default function ShiftsPage() {
  const { data, loading, error } = useApi<Shift[]>("/shifts");

  return (
    <>
      <PageHeader title="Shifts" subtitle="Shift state, scheduled vs actual." />

      {error && <div className={p.errBanner}>{error}</div>}

      <Card>
        {loading ? (
          <SkeletonRows rows={8} />
        ) : !data || data.length === 0 ? (
          <Empty title="No shifts" hint="Shifts appear once schedules generate or employees start." />
        ) : (
          <table className={p.table}>
            <thead>
              <tr>
                <th>State</th>
                <th>Scheduled start</th>
                <th>Scheduled end</th>
                <th>Actual start</th>
                <th>Actual end</th>
                <th>Timezone</th>
              </tr>
            </thead>
            <tbody>
              {data.map((s, i) => (
                <motion.tr
                  key={s.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: Math.min(i * 0.025, 0.4) }}
                >
                  <td>
                    <Badge label={s.state} />
                  </td>
                  <td className={p.mono}>{timeOfDay(s.scheduled_start)}</td>
                  <td className={p.mono}>{timeOfDay(s.scheduled_end)}</td>
                  <td className={p.mono}>{timeOfDay(s.actual_start)}</td>
                  <td className={p.mono}>{timeOfDay(s.actual_end)}</td>
                  <td className="muted">{s.timezone}</td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
