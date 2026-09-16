"use client";

import { motion } from "framer-motion";
import styles from "./ui.module.css";

/* ---------------- Card ---------------- */
export function Card({
  children,
  className = "",
  delay = 0,
  hover = false,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
  hover?: boolean;
}) {
  return (
    <motion.div
      className={`glass ${styles.card} ${hover ? styles.cardHover : ""} ${className}`}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1], delay }}
    >
      {children}
    </motion.div>
  );
}

/* ---------------- Animated counter ---------------- */
export function Counter({ value, decimals = 0 }: { value: number; decimals?: number }) {
  return (
    <motion.span
      key={value}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      {value.toLocaleString(undefined, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}
    </motion.span>
  );
}

/* ---------------- Stat ---------------- */
export function Stat({
  label,
  value,
  accent = "var(--accent)",
  suffix,
  delay = 0,
}: {
  label: string;
  value: React.ReactNode;
  accent?: string;
  suffix?: string;
  delay?: number;
}) {
  return (
    <Card delay={delay} hover>
      <div className={styles.statDot} style={{ background: accent }} />
      <div className={styles.statValue}>
        {value}
        {suffix && <span className={styles.statSuffix}>{suffix}</span>}
      </div>
      <div className={styles.statLabel}>{label}</div>
    </Card>
  );
}

/* ---------------- Badge ---------------- */
const STATUS_COLOR: Record<string, string> = {
  WORKING: "var(--ok)",
  PRESENT: "var(--ok)",
  ON_BREAK: "var(--warn)",
  PAUSED: "var(--warn)",
  LATE: "var(--warn)",
  OVERTIME: "var(--info)",
  COMPLETED: "var(--text-dim)",
  AUTO_COMPLETED: "var(--text-dim)",
  MISSED: "var(--danger)",
  MISSED_SHIFT: "var(--danger)",
  ABSENT: "var(--danger)",
  OFFLINE: "var(--text-faint)",
  NOT_STARTED: "var(--text-faint)",
  critical: "var(--danger)",
  warning: "var(--warn)",
  info: "var(--info)",
};

export function Badge({ label }: { label: string }) {
  const color = STATUS_COLOR[label] || "var(--text-dim)";
  return (
    <span className={styles.badge} style={{ color, borderColor: color }}>
      <span className={styles.badgeDot} style={{ background: color }} />
      {label.replace(/_/g, " ").toLowerCase()}
    </span>
  );
}

/* ---------------- Ring (productivity indicator) ---------------- */
export function Ring({ value, size = 132 }: { value: number; size?: number }) {
  const r = (size - 14) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className={styles.ring} style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <defs>
          <linearGradient id="ringgrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#6c8cff" />
            <stop offset="60%" stopColor="#9b6cff" />
            <stop offset="100%" stopColor="#35d6c3" />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(255,255,255,0.08)" strokeWidth="10" fill="none" />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke="url(#ringgrad)"
          strokeWidth="10"
          fill="none"
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c - (c * pct) / 100 }}
          transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
        />
      </svg>
      <div className={styles.ringLabel}>
        <span className={styles.ringValue}>{Math.round(pct)}%</span>
        <span className={styles.ringCap}>indicator</span>
      </div>
    </div>
  );
}

/* ---------------- Spinner ---------------- */
export function Spinner({ size = 22 }: { size?: number }) {
  return (
    <div
      className={styles.spinner}
      style={{ width: size, height: size, borderWidth: Math.max(2, size / 10) }}
    />
  );
}

/* ---------------- Skeleton rows ---------------- */
export function SkeletonRows({ rows = 6 }: { rows?: number }) {
  return (
    <div className={styles.skelWrap}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 46 }} />
      ))}
    </div>
  );
}

/* ---------------- Empty state ---------------- */
export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyMark}>∅</div>
      <div className={styles.emptyTitle}>{title}</div>
      {hint && <div className={styles.emptyHint}>{hint}</div>}
    </div>
  );
}

/* ---------------- Page header ---------------- */
export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return (
    <motion.div
      className={styles.pageHeader}
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div>
        <h1 className={styles.pageTitle}>{title}</h1>
        {subtitle && <p className={styles.pageSub}>{subtitle}</p>}
      </div>
      {action}
    </motion.div>
  );
}

/* ---------------- Avatar ---------------- */
export function Avatar({ name }: { name: string }) {
  const init = name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() || "")
    .join("");
  return <div className={styles.avatar}>{init}</div>;
}
