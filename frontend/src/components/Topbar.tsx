"use client";

import { motion } from "framer-motion";
import { useAuth } from "@/lib/auth";
import { Avatar } from "./ui";
import styles from "./shell.module.css";

export function Topbar() {
  const { me, logout } = useAuth();
  const role = me?.roles?.[0]?.replace(/_/g, " ") || "member";

  return (
    <motion.header
      className={styles.topbar}
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div className={styles.search}>
        <span>⌕</span>
        <input placeholder="Search employees, teams, shifts…" />
      </div>

      <div className={styles.topRight}>
        <div className={styles.pulse}>
          <span className={styles.pulseDot} /> Live
        </div>
        <div className={styles.userChip}>
          <div className={styles.userMeta}>
            <div className={styles.userName}>{me?.email}</div>
            <div className={styles.userRole}>{role}</div>
          </div>
          <Avatar name={me?.email || "U"} />
        </div>
        <button className={styles.logout} onClick={logout} title="Sign out">
          ⎋
        </button>
      </div>
    </motion.header>
  );
}
