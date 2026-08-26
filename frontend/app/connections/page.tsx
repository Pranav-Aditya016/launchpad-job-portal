"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  ApiError,
  disconnectConnection,
  getConnections,
  startConnectionLogin,
  verifyConnection,
  type Connection,
} from "@/lib/api";
import { NavBar } from "@/components/NavBar";
import { Button } from "@/components/Button";
import { Badge } from "@/components/Badge";
import { GlassCard } from "@/components/GlassCard";
import { EmptyState } from "@/components/EmptyState";
import { StatusDot, STATUS_LABEL } from "@/components/StatusDot";
import { relativeDate } from "@/lib/utils";

const STATUS_TONE: Record<Connection["status"], "neutral" | "success" | "warning" | "accent" | "danger"> = {
  disconnected: "neutral",
  connected: "success",
  expired: "warning",
  checking: "accent",
  blocked: "danger",
};

type Busy = "login" | "verify" | "disconnect" | null;

export default function ConnectionsPage() {
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyPortal, setBusyPortal] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<Busy>(null);
  const [notices, setNotices] = useState<Record<string, { tone: "info" | "danger"; text: string }>>({});

  // Reusable re-fetch for post-action refreshes (event handlers, not effects).
  const load = useCallback(async () => {
    try {
      const res = await getConnections();
      setConnections(res.connections);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Couldn't load your connections.");
    }
  }, []);

  // Mount fetch — ignore-flag guarded so a fast unmount can't set state on a
  // gone component, matching the bootstrap() pattern used elsewhere in this app.
  useEffect(() => {
    let ignore = false;
    async function bootstrap() {
      try {
        const res = await getConnections();
        if (ignore) return;
        setConnections(res.connections);
        setLoadError(null);
      } catch (e) {
        if (ignore) return;
        setLoadError(e instanceof ApiError ? e.message : "Couldn't load your connections.");
      }
    }
    bootstrap();
    return () => {
      ignore = true;
    };
  }, []);

  function setNotice(portal: string, tone: "info" | "danger", text: string) {
    setNotices((n) => ({ ...n, [portal]: { tone, text } }));
  }

  async function runAction(
    portal: string,
    action: Busy,
    fn: (portal: string) => Promise<{ ok: boolean; notYetImplemented: boolean; message?: string }>
  ) {
    setBusyPortal(portal);
    setBusyAction(action);
    setNotices((n) => {
      const next = { ...n };
      delete next[portal];
      return next;
    });
    try {
      const res = await fn(portal);
      if (res.notYetImplemented) {
        setNotice(
          portal,
          "info",
          "This is coming online shortly — the team building portal logins hasn't landed it yet. Check back soon."
        );
      } else {
        await load();
      }
    } catch (e) {
      setNotice(
        portal,
        "danger",
        e instanceof ApiError ? e.message : "Something went wrong. Please try again."
      );
    } finally {
      setBusyPortal(null);
      setBusyAction(null);
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <NavBar />
      <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-6 py-10">
        <div className="flex flex-col gap-1">
          <h1 className="font-display text-title">Connections</h1>
          <p className="text-body text-muted">
            Portals that need you signed in before LaunchPad can look there.
          </p>
        </div>

        {/* Trust-critical explanation — prominent, not buried fine print. */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", bounce: 0, duration: 0.4 }}
        >
          <GlassCard innerClassName="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-4">
            <div
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full"
              style={{ background: "var(--success-wash)" }}
              aria-hidden="true"
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--success)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="11" width="18" height="10" rx="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
            </div>
            <div className="flex flex-col gap-1">
              <p className="font-display text-headline">Your logins stay yours</p>
              <p className="text-body text-muted">
                LaunchPad opens a real browser window and <strong className="text-foreground">you</strong> log
                in yourself. It never sees or stores your password — only the browser session that
                results stays on this machine, the same way your everyday browser remembers you.
              </p>
            </div>
          </GlassCard>
        </motion.div>

        {loadError && (
          <div className="rounded-xl bg-[color:var(--danger-wash)] px-4 py-3 text-body text-danger">
            {loadError}
          </div>
        )}

        {connections === null && !loadError && (
          <div className="flex flex-col gap-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-28 animate-pulse rounded-[var(--radius-card)] bg-surface-2" />
            ))}
          </div>
        )}

        {connections && connections.length === 0 && (
          <EmptyState
            title="No portals registered yet"
            description="Login-gated sources are still being wired up behind the scenes. Once they're registered, they'll show up here for you to connect."
          />
        )}

        {connections && connections.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {connections.map((conn) => {
              const isBusy = busyPortal === conn.portal;
              const notice = notices[conn.portal];
              const verified = relativeDate(conn.last_verified);
              return (
                <GlassCard key={conn.portal} innerClassName="flex flex-col gap-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex flex-col gap-1 min-w-0">
                      <p className="font-display text-headline truncate">{conn.label}</p>
                      <div className="flex items-center gap-1.5">
                        <StatusDot status={conn.status} />
                        <span className="text-caption text-muted">{STATUS_LABEL[conn.status]}</span>
                      </div>
                    </div>
                    <Badge tone={STATUS_TONE[conn.status]}>{conn.status}</Badge>
                  </div>

                  {conn.login_url && (
                    <p className="text-caption text-muted truncate">{conn.login_url}</p>
                  )}

                  {verified && (
                    <p className="text-caption text-muted">Last verified {verified}</p>
                  )}

                  {conn.note && (
                    <p className="text-caption text-muted">{conn.note}</p>
                  )}

                  {conn.warning && (
                    <div className="rounded-xl bg-[color:var(--warning-wash)] px-3 py-2 text-caption text-warning">
                      {conn.warning}
                    </div>
                  )}

                  {notice && notice.text && (
                    <div
                      className={
                        notice.tone === "danger"
                          ? "rounded-xl bg-[color:var(--danger-wash)] px-3 py-2 text-caption text-danger"
                          : "rounded-xl bg-[color:var(--accent-wash)] px-3 py-2 text-caption text-accent"
                      }
                    >
                      {notice.text}
                    </div>
                  )}

                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    {(conn.status === "disconnected" || conn.status === "expired") && (
                      <Button
                        size="sm"
                        loading={isBusy && busyAction === "login"}
                        disabled={isBusy}
                        onClick={() => runAction(conn.portal, "login", startConnectionLogin)}
                      >
                        {conn.status === "expired" ? "Reconnect" : "Connect"}
                      </Button>
                    )}
                    {conn.status === "connected" && (
                      <Button
                        size="sm"
                        variant="secondary"
                        loading={isBusy && busyAction === "verify"}
                        disabled={isBusy}
                        onClick={() => runAction(conn.portal, "verify", verifyConnection)}
                      >
                        Verify
                      </Button>
                    )}
                    {conn.status !== "disconnected" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        loading={isBusy && busyAction === "disconnect"}
                        disabled={isBusy}
                        onClick={() => runAction(conn.portal, "disconnect", disconnectConnection)}
                      >
                        Disconnect
                      </Button>
                    )}
                  </div>
                </GlassCard>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
