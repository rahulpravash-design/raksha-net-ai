"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

import {
  ApiError,
  formatDateTime,
  type AppNotification,
  type NotificationKind,
} from "@raksha/api-client";

/** The slice of the API client this component needs — and nothing else. */
export interface NotificationApi {
  notifications(query?: {
    page_size?: number;
    unread_only?: boolean;
  }): Promise<{ items: AppNotification[]; total: number }>;
  unreadNotificationCount(): Promise<number>;
  markNotificationRead(id: string): Promise<AppNotification>;
  markAllNotificationsRead(): Promise<void>;
}

const KIND_LABELS: Record<NotificationKind, string> = {
  INCIDENT_STATUS_CHANGED: "Status update",
  INCIDENT_RECEIVED: "New incident",
  DISPATCH_ASSIGNED: "Assignment",
  DISPATCH_CANCELLED: "Stood down",
  HOSPITAL_NOTICE: "Hospital notice",
  SYSTEM: "System",
};

export function notificationKindLabel(kind: NotificationKind): string {
  return KIND_LABELS[kind] ?? kind;
}

/** Channels other than in-app that were recorded as not sent. */
export function undeliveredChannels(notification: AppNotification): string[] {
  return notification.deliveries
    .filter((d) => d.channel !== "IN_APP" && d.status !== "DELIVERED")
    .map((d) => d.channel);
}

const POLL_MS = 30_000;
const PAGE_SIZE = 20;

/**
 * Bell + unread badge + inbox panel, shared by all three apps.
 *
 * Only the in-app channel delivers today (SMS, email and push are stubbed), and
 * the panel says so for any notification that expected another channel — an
 * operator should never assume a text message went out when none was sent.
 * The count is polled while the tab is visible; there is no push channel.
 */
export function NotificationBell({
  api,
  hrefFor,
  navigate,
}: {
  api: NotificationApi;
  /** Where a notification leads, or null when it has no destination here. */
  hrefFor: (notification: AppNotification) => string | null;
  /** Called to follow a link (the host app's router). */
  navigate: (href: string) => void;
}) {
  const panelId = useId();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<AppNotification[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  const refreshCount = useCallback(async () => {
    try {
      setUnread(await api.unreadNotificationCount());
    } catch {
      // A failed badge poll must not interrupt anyone; the next poll retries.
    }
  }, [api]);

  const loadList = useCallback(async () => {
    try {
      const page = await api.notifications({ page_size: PAGE_SIZE });
      setItems(page.items);
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Notifications could not be loaded.",
      );
    }
  }, [api]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshCount();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refreshCount();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [refreshCount]);

  useEffect(() => {
    if (!open) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadList();
    const onPointer = (event: PointerEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, loadList]);

  async function openItem(notification: AppNotification) {
    const href = hrefFor(notification);
    if (!notification.read_at) {
      try {
        await api.markNotificationRead(notification.id);
        setItems(
          (current) =>
            current?.map((n) =>
              n.id === notification.id
                ? { ...n, read_at: new Date().toISOString() }
                : n,
            ) ?? null,
        );
        setUnread((count) => Math.max(0, count - 1));
      } catch {
        // Reading failed server-side; leave it unread rather than pretend.
      }
    }
    if (href) {
      setOpen(false);
      navigate(href);
    }
  }

  async function markAll() {
    setBusy(true);
    try {
      await api.markAllNotificationsRead();
      await Promise.all([loadList(), refreshCount()]);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Could not mark notifications as read.",
      );
    } finally {
      setBusy(false);
    }
  }

  const label =
    unread > 0 ? `Notifications, ${unread} unread` : "Notifications, none unread";

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className="surface relative inline-flex h-10 w-10 items-center justify-center rounded-lg"
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M6 9a6 6 0 1 1 12 0c0 5 2 6.5 2 6.5H4S6 14 6 9Z" />
          <path d="M10 19a2 2 0 0 0 4 0" />
        </svg>
        {unread > 0 && (
          <span
            aria-hidden="true"
            className="absolute -right-1 -top-1 min-w-5 rounded-full bg-red-600 px-1 text-center text-xs font-bold leading-5 text-white"
          >
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <section
          id={panelId}
          aria-label="Notifications"
          className="surface absolute right-0 z-50 mt-2 w-[min(24rem,calc(100vw-2rem))] rounded-xl p-3 shadow-xl"
        >
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-semibold">Notifications</h2>
            <button
              type="button"
              disabled={busy || unread === 0}
              onClick={() => void markAll()}
              className="text-sm font-semibold underline disabled:cursor-not-allowed disabled:no-underline disabled:opacity-50"
            >
              Mark all read
            </button>
          </div>

          {error && (
            <p role="alert" className="mt-2 text-sm text-red-600">
              {error}
            </p>
          )}
          {items === null && !error && <p className="muted mt-3 text-sm">Loading…</p>}
          {items !== null && items.length === 0 && (
            <p className="muted mt-3 text-sm">You have no notifications.</p>
          )}

          {items !== null && items.length > 0 && (
            <ul className="mt-2 max-h-[min(28rem,70vh)] space-y-2 overflow-y-auto">
              {items.map((notification) => {
                const missed = undeliveredChannels(notification);
                return (
                  <li key={notification.id}>
                    <button
                      type="button"
                      onClick={() => void openItem(notification)}
                      className="w-full rounded-lg border border-[var(--border)] p-2 text-left"
                    >
                      <span className="flex items-center justify-between gap-2 text-xs">
                        <span className="font-semibold">
                          {notification.read_at ? "" : "● "}
                          {notificationKindLabel(notification.kind)}
                          {!notification.read_at && (
                            <span className="sr-only"> (unread)</span>
                          )}
                        </span>
                        <span className="muted">
                          {formatDateTime(notification.created_at)}
                        </span>
                      </span>
                      <span
                        className={`mt-1 block text-sm ${
                          notification.read_at ? "" : "font-semibold"
                        }`}
                      >
                        {notification.title}
                      </span>
                      <span className="muted block text-xs">{notification.body}</span>
                      {missed.length > 0 && (
                        <span className="muted mt-1 block text-xs italic">
                          Delivered in the app only — {missed.join(", ")} not sent.
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
