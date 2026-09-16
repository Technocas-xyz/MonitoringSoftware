"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useApi } from "@/lib/useApi";
import type { Employee } from "@/lib/types";
import { Badge, Card, PageHeader, SkeletonRows, Empty, Avatar } from "@/components/ui";
import p from "../pages.module.css";

export default function EmployeesPage() {
  const { data, loading, error } = useApi<Employee[]>("/employees");
  const [q, setQ] = useState("");
  const router = useRouter();

  const filtered = useMemo(() => {
    const list = data || [];
    if (!q.trim()) return list;
    const t = q.toLowerCase();
    return list.filter(
      (e) => e.full_name.toLowerCase().includes(t) || (e.employee_code || "").toLowerCase().includes(t)
    );
  }, [data, q]);

  return (
    <>
      <PageHeader title="Employees" subtitle="Directory and per-employee productivity." />

      {error && <div className={p.errBanner}>{error}</div>}

      <div className={p.filters}>
        <input
          className={p.input}
          placeholder="Search by name or code…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ minWidth: 260 }}
        />
      </div>

      <Card>
        {loading ? (
          <SkeletonRows rows={8} />
        ) : filtered.length === 0 ? (
          <Empty title="No employees found" hint={q ? "Try a different search." : "Create employees in the backend to populate this list."} />
        ) : (
          <table className={p.table}>
            <thead>
              <tr>
                <th>Employee</th>
                <th>Code</th>
                <th>Status</th>
                <th>Timezone</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e, i) => (
                <motion.tr
                  key={e.id}
                  className={p.rowLink}
                  onClick={() => router.push(`/employees/${e.id}`)}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: Math.min(i * 0.025, 0.4) }}
                >
                  <td>
                    <div className={p.nameCell}>
                      <Avatar name={e.full_name} />
                      <div className={p.nameMain}>{e.full_name}</div>
                    </div>
                  </td>
                  <td className={p.mono}>{e.employee_code || "—"}</td>
                  <td>
                    <Badge label={e.status.toUpperCase()} />
                  </td>
                  <td className="muted">{e.timezone || "org default"}</td>
                  <td style={{ textAlign: "right", color: "var(--text-faint)" }}>›</td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
