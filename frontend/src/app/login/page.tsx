"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import styles from "./login.module.css";

export default function LoginPage() {
  const { login, me, loading } = useAuth();
  const router = useRouter();
  const [org, setOrg] = useState("platform");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && me) router.replace("/dashboard");
  }, [loading, me, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(org.trim(), email.trim(), password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to sign in");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.wrap}>
      <div className="aurora" aria-hidden>
        <span />
        <span />
        <span />
      </div>

      <motion.div
        className={styles.showcase}
        initial={{ opacity: 0, x: -30 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className={styles.brand}>
          <div className={styles.logo}>◆</div>
          <span>Sentry</span>
        </div>
        <h1 className={styles.headline}>
          See how your <span className="gradient-text">team truly works</span>.
        </h1>
        <p className={styles.sub}>
          Attendance, time tracking, and productivity analytics — unified in one calm,
          real‑time workspace.
        </p>
        <div className={styles.pills}>
          {["Live presence", "Smart shifts", "Productivity insight", "Private by design"].map(
            (t, i) => (
              <motion.span
                key={t}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 + i * 0.08 }}
              >
                {t}
              </motion.span>
            )
          )}
        </div>
      </motion.div>

      <motion.form
        onSubmit={onSubmit}
        className={`glass ${styles.card}`}
        initial={{ opacity: 0, y: 30, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: 0.1 }}
      >
        <h2 className={styles.title}>Welcome back</h2>
        <p className={styles.hint}>Sign in to your organization workspace.</p>

        <label className={styles.field}>
          <span>Organization</span>
          <input value={org} onChange={(e) => setOrg(e.target.value)} placeholder="acme" required />
        </label>
        <label className={styles.field}>
          <span>Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            required
          />
        </label>
        <label className={styles.field}>
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
          />
        </label>

        {error && (
          <motion.div className={styles.error} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            {error}
          </motion.div>
        )}

        <motion.button
          className={styles.submit}
          type="submit"
          disabled={busy}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          {busy ? "Signing in…" : "Sign in"}
        </motion.button>

        <p className={styles.foot}>
          Secured with role‑based access & tenant isolation.
        </p>
      </motion.form>
    </div>
  );
}
