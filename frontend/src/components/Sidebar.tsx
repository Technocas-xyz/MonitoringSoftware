"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { useAuth } from "@/lib/auth";
import styles from "./shell.module.css";

type NavItem = { href: string; label: string; icon: string; perm?: string };

const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: "◧" },
  { href: "/live", label: "Live board", icon: "◉", perm: "analytics.view" },
  { href: "/employees", label: "Employees", icon: "◍", perm: "employee.view" },
  { href: "/attendance", label: "Attendance", icon: "◔", perm: "attendance.view" },
  { href: "/shifts", label: "Shifts", icon: "◐", perm: "shift.view" },
  { href: "/alerts", label: "Alerts", icon: "◆", perm: "alert.view" },
  { href: "/settings", label: "Settings", icon: "⚙", perm: "settings.manage" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { has } = useAuth();

  return (
    <aside className={`glass ${styles.sidebar}`}>
      <div className={styles.brand}>
        <div className={styles.logo}>◆</div>
        <span>Sentry</span>
      </div>

      <nav className={styles.nav}>
        {NAV.filter((n) => !n.perm || has(n.perm)).map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link key={item.href} href={item.href} className={styles.navLink}>
              {active && (
                <motion.span
                  layoutId="nav-active"
                  className={styles.navActive}
                  transition={{ type: "spring", stiffness: 400, damping: 32 }}
                />
              )}
              <span className={styles.navIcon}>{item.icon}</span>
              <span className={styles.navLabel}>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className={styles.sidebarFoot}>
        <div className={styles.footTag}>v0.1 · Preview</div>
      </div>
    </aside>
  );
}
