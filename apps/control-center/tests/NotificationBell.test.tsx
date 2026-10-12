import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type AppNotification } from "@raksha/api-client";
import { NotificationBell, type NotificationApi } from "@raksha/ui";

function notification(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: "n1",
    kind: "INCIDENT_RECEIVED",
    title: "New incident reported",
    body: "Flood near the market",
    incident_id: "inc-1",
    dispatch_id: null,
    context: null,
    read_at: null,
    created_at: "2026-01-01T09:00:00Z",
    deliveries: [
      { channel: "IN_APP", status: "DELIVERED", attempts: 1, detail: null, delivered_at: null },
      { channel: "SMS", status: "UNAVAILABLE", attempts: 0, detail: "no provider", delivered_at: null },
    ],
    ...overrides,
  };
}

const api = {
  notifications: vi.fn(),
  unreadNotificationCount: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
} satisfies NotificationApi;

const navigate = vi.fn();
const hrefFor = (n: AppNotification) => (n.incident_id ? `/incidents/${n.incident_id}` : null);

function renderBell() {
  render(<NotificationBell api={api} hrefFor={hrefFor} navigate={navigate} />);
}

beforeEach(() => {
  api.notifications.mockReset().mockResolvedValue({ items: [notification()], total: 1 });
  api.unreadNotificationCount.mockReset().mockResolvedValue(1);
  api.markNotificationRead.mockReset().mockResolvedValue(notification());
  api.markAllNotificationsRead.mockReset().mockResolvedValue(undefined);
  navigate.mockReset();
});

describe("NotificationBell", () => {
  it("announces the unread count on the button, not by colour alone", async () => {
    renderBell();
    expect(
      await screen.findByRole("button", { name: "Notifications, 1 unread" }),
    ).toBeInTheDocument();
  });

  it("says when nothing is unread", async () => {
    api.unreadNotificationCount.mockResolvedValue(0);
    renderBell();
    expect(
      await screen.findByRole("button", { name: "Notifications, none unread" }),
    ).toBeInTheDocument();
  });

  it("lists notifications, and states which channels were not sent", async () => {
    renderBell();
    await userEvent.click(await screen.findByRole("button", { name: /notifications/i }));

    expect(await screen.findByText("New incident reported")).toBeInTheDocument();
    expect(screen.getByText(/delivered in the app only — sms not sent/i)).toBeInTheDocument();
  });

  it("marks the item read and follows its link", async () => {
    renderBell();
    await userEvent.click(await screen.findByRole("button", { name: /notifications/i }));
    await userEvent.click(await screen.findByText("New incident reported"));

    await waitFor(() => expect(api.markNotificationRead).toHaveBeenCalledWith("n1"));
    expect(navigate).toHaveBeenCalledWith("/incidents/inc-1");
    expect(
      await screen.findByRole("button", { name: "Notifications, none unread" }),
    ).toBeInTheDocument();
  });

  it("marks everything read", async () => {
    renderBell();
    await userEvent.click(await screen.findByRole("button", { name: /notifications/i }));
    await userEvent.click(await screen.findByRole("button", { name: /mark all read/i }));

    await waitFor(() => expect(api.markAllNotificationsRead).toHaveBeenCalled());
  });

  it("does not navigate for a notification with no destination", async () => {
    api.notifications.mockResolvedValue({
      items: [notification({ incident_id: null, title: "System notice" })],
      total: 1,
    });
    renderBell();
    await userEvent.click(await screen.findByRole("button", { name: /notifications/i }));
    await userEvent.click(await screen.findByText("System notice"));

    expect(navigate).not.toHaveBeenCalled();
  });

  it("shows a load failure rather than an empty inbox", async () => {
    api.notifications.mockRejectedValue(
      new ApiError(503, { code: "SERVICE_BUSY", message: "The system is very busy." }),
    );
    renderBell();
    await userEvent.click(await screen.findByRole("button", { name: /notifications/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/very busy/i);
    expect(screen.queryByText(/no notifications/i)).toBeNull();
  });

  it("closes on Escape", async () => {
    renderBell();
    await userEvent.click(await screen.findByRole("button", { name: /notifications/i }));
    expect(await screen.findByRole("region", { name: "Notifications" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("region", { name: "Notifications" })).toBeNull();
  });
});
