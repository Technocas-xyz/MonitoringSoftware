"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useApi } from "@/lib/useApi";
import { api, ApiError } from "@/lib/api";
import type { Employee } from "@/lib/types";
import { Badge, Button, Card, PageHeader, SkeletonRows, Empty, Avatar, Modal } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import u from "@/components/ui.module.css";
import p from "../pages.module.css";

export default function EmployeesPage() {
  const { has } = useAuth();
  const canManage = has("employee.manage");
  const { data, loading, error, reload } = useApi<Employee[]>("/employees");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
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
      <PageHeader
        title="Employees"
        subtitle="Directory and per-employee productivity."
        action={
          canManage ? (
            <Button onClick={() => setOpen(true)}>+ New employee</Button>
          ) : undefined
        }
      />

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
          <Empty
            title="No employees found"
            hint={
              q
                ? "Try a different search."
                : canManage
                ? "Add your first employee to get started."
                : "No employees yet."
            }
          />
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

      <NewEmployeeModal
        open={open}
        onClose={() => setOpen(false)}
        onCreated={() => {
          setOpen(false);
          reload();
        }}
      />
    </>
  );
}

function NewEmployeeModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [fullName, setFullName] = useState("");
  const [code, setCode] = useState("");
  const [timezone, setTimezone] = useState("");
  const [hiredAt, setHiredAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!fullName.trim()) {
      setErr("Full name is required.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api("/employees", {
        method: "POST",
        body: {
          full_name: fullName.trim(),
          employee_code: code.trim() || null,
          timezone: timezone.trim() || null,
          hired_at: hiredAt || null,
        },
      });
      setFullName("");
      setCode("");
      setTimezone("");
      setHiredAt("");
      onCreated();
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "Could not create employee.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="New employee">
      <form onSubmit={submit}>
        {err && <div className={p.errBanner}>{err}</div>}
        <label className={u.formField}>
          <span>Full name *</span>
          <input
            className={u.formInput}
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Jane Doe"
            autoFocus
          />
        </label>
        <label className={u.formField}>
          <span>Employee code</span>
          <input
            className={u.formInput}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="EMP-001"
          />
        </label>
        <label className={u.formField}>
          <span>Timezone</span>
          <input
            className={u.formInput}
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            placeholder="e.g. America/New_York (blank = org default)"
          />
        </label>
        <label className={u.formField}>
          <span>Hired date</span>
          <input
            type="date"
            className={u.formInput}
            value={hiredAt}
            onChange={(e) => setHiredAt(e.target.value)}
          />
        </label>
        <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy} full>
            {busy ? "Creating…" : "Create employee"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
