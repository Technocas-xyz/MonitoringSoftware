"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Badge, Button, Card, PageHeader, Modal, SkeletonRows, Empty, Avatar } from "@/components/ui";
import { useApi } from "@/lib/useApi";
import { api, ApiError, API_BASE } from "@/lib/api";
import type { Device, DeviceApproved, Employee } from "@/lib/types";
import { useAuth } from "@/lib/auth";
import u from "@/components/ui.module.css";
import p from "../pages.module.css";

type Download = {
  icon: string;
  title: string;
  desc: string;
  meta: string;
  primary?: boolean;
};

const DOWNLOADS: Download[] = [
  {
    icon: "🖥",
    title: "Windows Agent (Service + Tray)",
    desc:
      "The full agent: a background Windows Service that collects activity, plus a lightweight system-tray app so employees can see status, pause, and start/stop shifts.",
    meta: "Windows 10 / 11 · x64 · ~14 MB",
    primary: true,
  },
  {
    icon: "🧰",
    title: "Silent MSI (fleet deployment)",
    desc:
      "Unattended installer for IT teams. Push through Intune, GPO, or your RMM with an enrollment token baked in — zero end-user clicks.",
    meta: "MSI · machine-wide · auto-enroll",
  },
];

const STEPS = [
  {
    n: 1,
    title: "Add the employee first",
    body:
      "A device is always bound to an existing employee — deploying the agent does NOT create an employee automatically. Create the person in Employees before enrolling their machine.",
    code: "POST /employees",
  },
  {
    n: 2,
    title: "Download & install",
    body:
      "Run the installer on that employee's machine. The Windows Service registers to start on boot and the tray app appears in the notification area.",
  },
  {
    n: 3,
    title: "Enroll the device",
    body:
      "Enroll the machine here and pick the employee it belongs to (or the employee self-enrolls from the tray app). The device is created as Pending.",
    code: "POST /devices",
  },
  {
    n: 4,
    title: "Approve",
    body:
      "Approve the pending device below. Approval mints a one-time signing secret shown only once — the agent stores it securely via DPAPI.",
    code: "POST /devices/{id}/approve",
  },
  {
    n: 5,
    title: "Token & collect",
    body:
      "The agent exchanges the secret for a device token, HMAC-signs every request, and starts tracking apps / idle / shift events — queued in an encrypted local DB when offline.",
    code: "POST /auth/agent/token",
  },
];

export default function AgentPage() {
  const { has } = useAuth();
  const canEnroll = has("device.view");
  const canApprove = has("device.approve");

  const devices = useApi<Device[]>("/devices");
  const employees = useApi<Employee[]>("/employees");
  const empName = (id: string) =>
    employees.data?.find((e) => e.id === id)?.full_name || id.slice(0, 8);

  const [enrollOpen, setEnrollOpen] = useState(false);
  const [secret, setSecret] = useState<{ device: string; value: string } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);

  async function approve(d: Device) {
    setBusyId(d.id);
    setActionErr(null);
    try {
      const res = await api<DeviceApproved>(`/devices/${d.id}/approve`, { method: "POST" });
      if (res.signing_secret) {
        setSecret({ device: d.hostname || empName(d.employee_id), value: res.signing_secret });
      }
      devices.reload();
    } catch (e) {
      setActionErr(e instanceof ApiError ? e.message : "Approve failed.");
    } finally {
      setBusyId(null);
    }
  }

  async function revoke(d: Device) {
    setBusyId(d.id);
    setActionErr(null);
    try {
      await api(`/devices/${d.id}/revoke`, { method: "POST" });
      devices.reload();
    } catch (e) {
      setActionErr(e instanceof ApiError ? e.message : "Revoke failed.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Deploy the agent"
        subtitle="Install the desktop agent on employee machines, enroll the device, then approve it to start collecting activity."
        action={
          canEnroll ? (
            <Button onClick={() => setEnrollOpen(true)}>+ Enroll device</Button>
          ) : undefined
        }
      />

      {/* Download cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
          gap: 16,
          marginBottom: 24,
        }}
      >
        {DOWNLOADS.map((d, i) => (
          <Card key={d.title} delay={0.05 * i} hover>
            <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
              <div
                style={{
                  fontSize: 26,
                  width: 52,
                  height: 52,
                  borderRadius: 14,
                  display: "grid",
                  placeItems: "center",
                  background: d.primary ? "var(--grad-primary)" : "var(--surface-tint)",
                  flexShrink: 0,
                }}
              >
                {d.icon}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700, fontSize: 16 }}>{d.title}</div>
                <p className="muted" style={{ fontSize: 13.5, marginTop: 6, lineHeight: 1.55 }}>
                  {d.desc}
                </p>
                <div className="faint" style={{ fontSize: 12, marginTop: 10 }}>
                  {d.meta}
                </div>
                <div style={{ marginTop: 16 }}>
                  {d.primary ? (
                    <Button onClick={() => alert("The agent build is not published in this local demo yet.")}>
                      ⬇  Download agent
                    </Button>
                  ) : (
                    <Button variant="ghost" onClick={() => alert("MSI build is not published in this local demo yet.")}>
                      Get MSI
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Devices panel */}
      <Card delay={0.12}>
        <div className={p.sectionTitle}>
          Devices
          {devices.data && devices.data.length > 0 && (
            <span className={p.nameSub}>{devices.data.length}</span>
          )}
        </div>
        {actionErr && <div className={p.errBanner}>{actionErr}</div>}
        {devices.loading ? (
          <SkeletonRows rows={3} />
        ) : devices.error ? (
          <div className={p.errBanner}>{devices.error}</div>
        ) : !devices.data || devices.data.length === 0 ? (
          <Empty
            title="No devices yet"
            hint={canEnroll ? "Enroll a device to see it here." : "No devices enrolled."}
          />
        ) : (
          <table className={p.table}>
            <thead>
              <tr>
                <th>Device</th>
                <th>Employee</th>
                <th>OS</th>
                <th>Status</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {devices.data.map((d, i) => (
                <motion.tr
                  key={d.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: Math.min(i * 0.03, 0.3) }}
                >
                  <td className={p.mono}>{d.hostname || "unnamed"}</td>
                  <td>
                    <div className={p.nameCell}>
                      <Avatar name={empName(d.employee_id)} />
                      <div className={p.nameMain}>{empName(d.employee_id)}</div>
                    </div>
                  </td>
                  <td className="muted">{d.os || "—"}</td>
                  <td>
                    <Badge label={d.status.toUpperCase()} />
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <div style={{ display: "inline-flex", gap: 8 }}>
                      {canApprove && d.status === "pending" && (
                        <Button onClick={() => approve(d)} disabled={busyId === d.id}>
                          {busyId === d.id ? "…" : "Approve"}
                        </Button>
                      )}
                      {canApprove && d.status === "approved" && (
                        <Button variant="danger" onClick={() => revoke(d)} disabled={busyId === d.id}>
                          {busyId === d.id ? "…" : "Revoke"}
                        </Button>
                      )}
                      {d.status === "revoked" && <span className="faint">revoked</span>}
                    </div>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {/* How it works + privacy */}
      <div className={p.split} style={{ marginTop: 24 }}>
        <Card delay={0.16}>
          <div className={p.sectionTitle}>How it works</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {STEPS.map((s, i) => (
              <motion.div
                key={s.n}
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.06 * i }}
                style={{ display: "flex", gap: 14, padding: "12px 0" }}
              >
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                  <div
                    style={{
                      width: 30,
                      height: 30,
                      borderRadius: 999,
                      display: "grid",
                      placeItems: "center",
                      background: "var(--grad-primary)",
                      color: "#fff",
                      fontWeight: 800,
                      fontSize: 13,
                      flexShrink: 0,
                    }}
                  >
                    {s.n}
                  </div>
                  {i < STEPS.length - 1 && (
                    <div style={{ flex: 1, width: 2, background: "var(--border)", marginTop: 4 }} />
                  )}
                </div>
                <div style={{ paddingBottom: 4 }}>
                  <div style={{ fontWeight: 700, fontSize: 14.5 }}>{s.title}</div>
                  <p className="muted" style={{ fontSize: 13, marginTop: 4, lineHeight: 1.55 }}>
                    {s.body}
                  </p>
                  {s.code && (
                    <code
                      style={{
                        display: "inline-block",
                        marginTop: 8,
                        padding: "4px 10px",
                        borderRadius: 8,
                        fontSize: 12,
                        background: "var(--surface-tint)",
                        border: "1px solid var(--border)",
                        color: "var(--accent)",
                        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                      }}
                    >
                      {s.code}
                    </code>
                  )}
                </div>
              </motion.div>
            ))}
          </div>
        </Card>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Card delay={0.2}>
            <div className={p.sectionTitle}>Privacy first</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {[
                "Never captures keystrokes, passwords, or clipboard contents.",
                "No screenshots unless your org explicitly enables it in policy.",
                "Offline queue is encrypted at rest on the device.",
                "Employees can see exactly what is tracked from the tray app.",
              ].map((line, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.06 * i }}
                  style={{ display: "flex", gap: 10, alignItems: "flex-start", fontSize: 13.5 }}
                >
                  <span style={{ color: "var(--ok)", fontWeight: 800 }}>✓</span>
                  <span className="muted" style={{ lineHeight: 1.5 }}>
                    {line}
                  </span>
                </motion.div>
              ))}
            </div>
          </Card>

          <Card delay={0.24}>
            <div className={p.sectionTitle}>Connection</div>
            <p className="muted" style={{ fontSize: 13, lineHeight: 1.55 }}>
              Agents report to this API endpoint. Make sure the machine can reach it.
            </p>
            <code
              style={{
                display: "block",
                marginTop: 10,
                padding: "10px 12px",
                borderRadius: 10,
                fontSize: 12.5,
                background: "var(--surface-tint)",
                border: "1px solid var(--border)",
                color: "var(--text)",
                wordBreak: "break-all",
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              }}
            >
              {API_BASE}
            </code>
          </Card>
        </div>
      </div>

      {/* Enroll modal */}
      <EnrollModal
        open={enrollOpen}
        onClose={() => setEnrollOpen(false)}
        employees={employees.data || []}
        onEnrolled={() => {
          setEnrollOpen(false);
          devices.reload();
        }}
      />

      {/* One-time signing secret reveal */}
      <Modal open={!!secret} onClose={() => setSecret(null)} title="Device approved" width={520}>
        <p className="muted" style={{ fontSize: 13.5, lineHeight: 1.55 }}>
          Copy this signing secret into the agent on <b>{secret?.device}</b>. It is shown only once and
          cannot be retrieved again — if you lose it, revoke and re-approve the device.
        </p>
        <code
          style={{
            display: "block",
            marginTop: 14,
            padding: "12px 14px",
            borderRadius: 10,
            fontSize: 13,
            background: "var(--surface-tint)",
            border: "1px solid var(--border-strong)",
            color: "var(--text)",
            wordBreak: "break-all",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          }}
        >
          {secret?.value}
        </code>
        <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
          <Button
            onClick={() => {
              if (secret?.value) navigator.clipboard?.writeText(secret.value);
            }}
          >
            Copy secret
          </Button>
          <Button variant="ghost" onClick={() => setSecret(null)}>
            Done
          </Button>
        </div>
      </Modal>
    </>
  );
}

function EnrollModal({
  open,
  onClose,
  employees,
  onEnrolled,
}: {
  open: boolean;
  onClose: () => void;
  employees: Employee[];
  onEnrolled: () => void;
}) {
  const [employeeId, setEmployeeId] = useState("");
  const [hostname, setHostname] = useState("");
  const [os, setOs] = useState("Windows");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!employeeId) {
      setErr("Pick an employee to bind this device to.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api("/devices", {
        method: "POST",
        body: {
          employee_id: employeeId,
          hostname: hostname.trim() || null,
          os: os.trim() || null,
        },
      });
      setEmployeeId("");
      setHostname("");
      onEnrolled();
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "Could not enroll device.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Enroll device">
      <form onSubmit={submit}>
        {err && <div className={p.errBanner}>{err}</div>}
        {employees.length === 0 ? (
          <Empty
            title="No employees yet"
            hint="Create an employee first — a device must be bound to a person."
          />
        ) : (
          <>
            <label className={u.formField}>
              <span>Employee *</span>
              <select
                className={u.formInput}
                value={employeeId}
                onChange={(e) => setEmployeeId(e.target.value)}
              >
                <option value="">Select an employee…</option>
                {employees.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.full_name}
                    {e.employee_code ? ` (${e.employee_code})` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className={u.formField}>
              <span>Hostname</span>
              <input
                className={u.formInput}
                value={hostname}
                onChange={(e) => setHostname(e.target.value)}
                placeholder="e.g. DESKTOP-A1B2C3"
              />
            </label>
            <label className={u.formField}>
              <span>OS</span>
              <input
                className={u.formInput}
                value={os}
                onChange={(e) => setOs(e.target.value)}
                placeholder="Windows"
              />
            </label>
            <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
              <Button variant="ghost" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={busy} full>
                {busy ? "Enrolling…" : "Enroll device"}
              </Button>
            </div>
          </>
        )}
      </form>
    </Modal>
  );
}
