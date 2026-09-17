"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAuth } from "@/lib/auth";
import { Card, PageHeader, SkeletonRows } from "@/components/ui";
import p from "../pages.module.css";

interface SettingsBlob {
  settings: Record<string, any>;
}

export default function SettingsPage() {
  const { me } = useAuth();
  const { data, loading, error, reload } = useApi<SettingsBlob>("/settings");
  const [toggles, setToggles] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data) {
      const s = data.settings || {};
      setToggles({
        sso: !!s.sso?.enabled,
        geo: !!s.geo?.enabled,
      });
    }
  }, [data]);

  async function save() {
    setSaving(true);
    setSaved(false);
    try {
      await api("/settings", {
        method: "PATCH",
        body: {
          settings: {
            sso: { enabled: toggles.sso },
            geo: { enabled: toggles.geo },
          },
        },
      });
      setSaved(true);
      reload();
      setTimeout(() => setSaved(false), 2500);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader title="Settings" subtitle="Organization configuration & your access." />

      {error && <div className={p.errBanner}>{error}</div>}

      <div className={p.split}>
        <Card>
          <div className={p.sectionTitle}>Optional modules</div>
          {loading ? (
            <SkeletonRows rows={3} />
          ) : (
            <>
              <ToggleRow
                label="Single sign-on (SSO)"
                hint="Allow login via configured identity providers."
                on={!!toggles.sso}
                onChange={(v) => setToggles((t) => ({ ...t, sso: v }))}
              />
              <ToggleRow
                label="Geolocation / geofencing"
                hint="Opt-in location pings + office geofence checks."
                on={!!toggles.geo}
                onChange={(v) => setToggles((t) => ({ ...t, geo: v }))}
              />
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 18 }}>
                <motion.button
                  className={p.input}
                  style={{ cursor: "pointer", background: "var(--grad-primary)", color: "#ffffff", fontWeight: 700, border: "none" }}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  disabled={saving}
                  onClick={save}
                >
                  {saving ? "Saving…" : "Save changes"}
                </motion.button>
                {saved && (
                  <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ color: "var(--ok)", fontSize: 13 }}>
                    ✓ Saved
                  </motion.span>
                )}
              </div>
            </>
          )}
        </Card>

        <Card delay={0.06}>
          <div className={p.sectionTitle}>Your access</div>
          <div style={{ fontSize: 14, marginBottom: 6 }}>{me?.email}</div>
          <div className="muted" style={{ fontSize: 13, marginBottom: 16, textTransform: "capitalize" }}>
            {me?.roles.join(", ").replace(/_/g, " ")}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
            {(me?.permissions || []).slice(0, 40).map((perm) => (
              <span
                key={perm}
                style={{
                  fontSize: 11.5,
                  padding: "4px 9px",
                  borderRadius: 999,
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  color: "var(--text-dim)",
                }}
              >
                {perm}
              </span>
            ))}
          </div>
        </Card>
      </div>
    </>
  );
}

function ToggleRow({
  label,
  hint,
  on,
  onChange,
}: {
  label: string;
  hint: string;
  on: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
        padding: "14px 0",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <div>
        <div style={{ fontWeight: 600, fontSize: 14 }}>{label}</div>
        <div className={p.nameSub}>{hint}</div>
      </div>
      <button
        onClick={() => onChange(!on)}
        aria-pressed={on}
        style={{
          width: 46,
          height: 26,
          borderRadius: 999,
          border: "1px solid var(--border)",
          background: on ? "var(--grad-primary)" : "var(--surface)",
          position: "relative",
          cursor: "pointer",
          transition: "background 0.2s",
          flexShrink: 0,
        }}
      >
        <motion.span
          layout
          transition={{ type: "spring", stiffness: 500, damping: 32 }}
          style={{
            position: "absolute",
            top: 2,
            left: on ? 22 : 2,
            width: 20,
            height: 20,
            borderRadius: 999,
            background: "#fff",
          }}
        />
      </button>
    </div>
  );
}
