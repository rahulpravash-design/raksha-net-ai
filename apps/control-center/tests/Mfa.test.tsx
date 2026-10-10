import { render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type User } from "@raksha/api-client";

import { MfaSettings, groupSecret } from "@/components/MfaSettings";
import { QrCode } from "@/components/QrCode";
import { SecondFactorField } from "@raksha/ui";

const client = {
  mfaEnroll: vi.fn(),
  mfaEnable: vi.fn(),
  mfaDisable: vi.fn(),
  mfaRecoveryStatus: vi.fn(),
  mfaRegenerateRecoveryCodes: vi.fn(),
};
const CODES = ["ABCD-EFGH-JKMN", "PQRS-TUVW-XYZA", "BCDF-GHJK-MNPQ"];
const refreshUser = vi.fn();
let currentUser: Partial<User> = {};
vi.mock("@/lib/api", () => ({ getApiClient: () => client }));
vi.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({ user: currentUser, refreshUser }),
}));

const URI = "otpauth://totp/RAKSHA:dana@example.com?secret=JBSWY3DPEHPK3PXP&issuer=RAKSHA";

beforeEach(() => {
  for (const fn of Object.values(client)) fn.mockReset();
  refreshUser.mockReset().mockResolvedValue(undefined);
  currentUser = { id: "u1", mfa_enabled: false };
  client.mfaEnroll.mockResolvedValue({ secret: "JBSWY3DPEHPK3PXP", provisioning_uri: URI });
  client.mfaEnable.mockResolvedValue({});
  client.mfaDisable.mockResolvedValue({});
  client.mfaRecoveryStatus.mockResolvedValue({ remaining: 10 });
  client.mfaRegenerateRecoveryCodes.mockResolvedValue(CODES);
});

describe("groupSecret", () => {
  it("splits into groups of four", () => {
    expect(groupSecret("JBSWY3DPEHPK3PXP")).toBe("JBSW Y3DP EHPK 3PXP");
    expect(groupSecret("ab cd")).toBe("abcd");
  });
});

describe("QrCode", () => {
  it("draws an accessible, dark-on-white code", () => {
    render(<QrCode value={URI} label="QR for the app" />);
    const svg = screen.getByRole("img", { name: "QR for the app" });
    expect(svg.querySelector("path")?.getAttribute("d")?.length).toBeGreaterThan(200);
    expect(svg).toHaveClass("bg-white");
  });
  it("renders different codes for different data", () => {
    const { container, rerender } = render(<QrCode value="aaaa" label="x" />);
    const first = container.querySelector("path")?.getAttribute("d");
    rerender(<QrCode value="bbbbbbbbbbbbbbbb" label="x" />);
    expect(container.querySelector("path")?.getAttribute("d")).not.toEqual(first);
  });
});

describe("MfaSettings — turning it on", () => {
  it("shows the QR, the key and the no-recovery warning, and sends nothing until a code is confirmed", async () => {
    render(<MfaSettings />);
    expect(screen.getByText("○ Off")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /set up two-factor/i }));

    expect(await screen.findByRole("img", { name: /qr code/i })).toBeInTheDocument();
    expect(screen.getByLabelText("Setup key")).toHaveTextContent("JBSW Y3DP EHPK 3PXP");
    expect(screen.getByText(/ten one-time recovery codes/i)).toBeInTheDocument();
    expect(client.mfaEnable).not.toHaveBeenCalled();
  });

  it("rejects a malformed code locally", async () => {
    render(<MfaSettings />);
    await userEvent.click(screen.getByRole("button", { name: /set up two-factor/i }));
    await userEvent.type(await screen.findByLabelText(/code from the app/i), "12ab");
    await userEvent.click(screen.getByRole("button", { name: /turn on/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/6-digit/i);
    expect(client.mfaEnable).not.toHaveBeenCalled();
  });

  it("confirms with the code, refreshes the user and says what changes", async () => {
    render(<MfaSettings />);
    await userEvent.click(screen.getByRole("button", { name: /set up two-factor/i }));
    await userEvent.type(await screen.findByLabelText(/code from the app/i), "123456");
    await userEvent.click(screen.getByRole("button", { name: /turn on/i }));
    await waitFor(() => expect(client.mfaEnable).toHaveBeenCalledWith("123456"));
    await waitFor(() => expect(refreshUser).toHaveBeenCalled());
    expect(await screen.findByRole("status")).toHaveTextContent(/asked for a code each time you sign in/i);
    expect(screen.queryByLabelText("Setup key")).toBeNull();
  });

  it("shows the server's message for a wrong code and keeps the enrolment open", async () => {
    client.mfaEnable.mockRejectedValue(new ApiError(400, { code: "INVALID_MFA_CODE", message: "That verification code is incorrect or has expired." }));
    render(<MfaSettings />);
    await userEvent.click(screen.getByRole("button", { name: /set up two-factor/i }));
    await userEvent.type(await screen.findByLabelText(/code from the app/i), "000000");
    await userEvent.click(screen.getByRole("button", { name: /turn on/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/incorrect or has expired/i);
    expect(screen.getByLabelText("Setup key")).toBeInTheDocument();
  });

  it("can be cancelled, discarding the key", async () => {
    render(<MfaSettings />);
    await userEvent.click(screen.getByRole("button", { name: /set up two-factor/i }));
    await userEvent.click(await screen.findByRole("button", { name: /cancel/i }));
    expect(screen.queryByLabelText("Setup key")).toBeNull();
    expect(screen.getByRole("button", { name: /set up two-factor/i })).toBeInTheDocument();
  });
});

describe("MfaSettings — turning it off", () => {
  beforeEach(() => {
    currentUser = { id: "u1", mfa_enabled: true };
  });

  it("asks for the password and a current code, after an explicit step", async () => {
    render(<MfaSettings />);
    expect(screen.getByText("● On")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /turn off two-factor…/i }));
    expect(client.mfaDisable).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /confirm turn off/i })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Password"), "hunter2-hunter2");
    await userEvent.type(screen.getByLabelText(/Current code or recovery code/), "654321");
    await userEvent.click(screen.getByRole("button", { name: /confirm turn off/i }));
    await waitFor(() => expect(client.mfaDisable).toHaveBeenCalledWith("hunter2-hunter2", "654321"));
    await waitFor(() => expect(refreshUser).toHaveBeenCalled());
  });

  it("shows a refusal and does not claim success", async () => {
    client.mfaDisable.mockRejectedValue(new ApiError(400, { code: "INVALID_MFA_CODE", message: "That verification code is incorrect or has expired." }));
    render(<MfaSettings />);
    await userEvent.click(screen.getByRole("button", { name: /turn off two-factor…/i }));
    await userEvent.type(screen.getByLabelText("Password"), "x");
    await userEvent.type(screen.getByLabelText(/Current code or recovery code/), "111111");
    await userEvent.click(screen.getByRole("button", { name: /confirm turn off/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/incorrect or has expired/i);
    expect(screen.queryByRole("status")).toBeNull();
    expect(refreshUser).not.toHaveBeenCalled();
  });
});


describe("MfaSettings — recovery codes", () => {
  it("holds the codes on screen after turning it on, until they are marked saved", async () => {
    client.mfaEnable.mockResolvedValue({ recovery_codes: CODES });
    render(<MfaSettings />);
    await userEvent.click(screen.getByRole("button", { name: /set up two-factor/i }));
    await userEvent.type(await screen.findByLabelText(/code from the app/i), "123456");
    await userEvent.click(screen.getByRole("button", { name: /turn on/i }));

    const group = await screen.findByRole("group", { name: "Recovery codes" });
    for (const code of CODES) expect(group).toHaveTextContent(code);
    expect(group).toHaveTextContent(/not shown again/i);
    const done = screen.getByRole("button", { name: "Done" });
    expect(done).toBeDisabled();

    await userEvent.click(screen.getByRole("checkbox", { name: /saved these codes/i }));
    expect(done).toBeEnabled();
    await userEvent.click(done);
    expect(screen.queryByRole("group", { name: "Recovery codes" })).toBeNull();
    // Gone for good: nothing on the page can bring them back.
    expect(document.body).not.toHaveTextContent(CODES[0]!);
  });

  it("copies the codes", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    client.mfaEnable.mockResolvedValue({ recovery_codes: CODES });
    render(<MfaSettings />);
    await userEvent.click(screen.getByRole("button", { name: /set up two-factor/i }));
    await userEvent.type(await screen.findByLabelText(/code from the app/i), "123456");
    await userEvent.click(screen.getByRole("button", { name: /turn on/i }));
    await userEvent.click(await screen.findByRole("button", { name: "Copy codes" }));
    expect(writeText).toHaveBeenCalledWith(CODES.join("\n"));
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  describe("with two-factor on", () => {
    beforeEach(() => {
      currentUser = { id: "u1", mfa_enabled: true };
    });

    it("says how many are left, and warns when they run low or out", async () => {
      client.mfaRecoveryStatus.mockResolvedValue({ remaining: 10 });
      const { unmount } = render(<MfaSettings />);
      expect(await screen.findByText("10 unused recovery codes.")).toBeInTheDocument();
      unmount();

      client.mfaRecoveryStatus.mockResolvedValue({ remaining: 2 });
      const second = render(<MfaSettings />);
      expect(await screen.findByText(/2 unused recovery codes — running low/)).toBeInTheDocument();
      second.unmount();

      client.mfaRecoveryStatus.mockResolvedValue({ remaining: 0 });
      render(<MfaSettings />);
      expect(await screen.findByText(/no recovery codes left.*need an administrator/i)).toBeInTheDocument();
    });

    it("does not break when the count cannot be fetched", async () => {
      client.mfaRecoveryStatus.mockRejectedValue(new ApiError(500, { code: "X", message: "down" }));
      render(<MfaSettings />);
      expect(await screen.findByText("Recovery codes: checking…")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /turn off two-factor/i })).toBeInTheDocument();
    });

    it("replaces the set after an explicit step, with the password and a code, and shows the new codes", async () => {
      render(<MfaSettings />);
      await userEvent.click(screen.getByRole("button", { name: /get new recovery codes/i }));
      expect(client.mfaRegenerateRecoveryCodes).not.toHaveBeenCalled();
      expect(screen.getByRole("button", { name: "Make new codes" })).toBeDisabled();

      await userEvent.type(screen.getByLabelText("Password"), "hunter2-hunter2");
      await userEvent.type(screen.getByLabelText(/Current code or recovery code/), "654321");
      await userEvent.click(screen.getByRole("button", { name: "Make new codes" }));

      await waitFor(() =>
        expect(client.mfaRegenerateRecoveryCodes).toHaveBeenCalledWith("hunter2-hunter2", "654321"),
      );
      const group = await screen.findByRole("group", { name: "Recovery codes" });
      expect(group).toHaveTextContent("Your new recovery codes");
      for (const code of CODES) expect(group).toHaveTextContent(code);
    });

    it("shows the server's refusal and keeps the old codes", async () => {
      client.mfaRegenerateRecoveryCodes.mockRejectedValue(
        new ApiError(400, { code: "INVALID_MFA_CODE", message: "That verification code is incorrect or has expired." }),
      );
      render(<MfaSettings />);
      await userEvent.click(screen.getByRole("button", { name: /get new recovery codes/i }));
      await userEvent.type(screen.getByLabelText("Password"), "x");
      await userEvent.type(screen.getByLabelText(/Current code or recovery code/), "111111");
      await userEvent.click(screen.getByRole("button", { name: "Make new codes" }));
      expect(await screen.findByRole("alert")).toHaveTextContent(/incorrect or has expired/i);
      expect(screen.queryByRole("group", { name: "Recovery codes" })).toBeNull();
    });

    it("turns two-factor off with a recovery code when the device is lost", async () => {
      render(<MfaSettings />);
      await userEvent.click(screen.getByRole("button", { name: /turn off two-factor…/i }));
      await userEvent.type(screen.getByLabelText("Password"), "hunter2-hunter2");
      await userEvent.type(screen.getByLabelText(/Current code or recovery code/), "abcd-efgh-jkmn");
      await userEvent.click(screen.getByRole("button", { name: /confirm turn off/i }));
      await waitFor(() =>
        expect(client.mfaDisable).toHaveBeenCalledWith("hunter2-hunter2", "abcd-efgh-jkmn"),
      );
    });

    it("refuses something that is neither kind of code without calling the server", async () => {
      render(<MfaSettings />);
      await userEvent.click(screen.getByRole("button", { name: /turn off two-factor…/i }));
      await userEvent.type(screen.getByLabelText("Password"), "x");
      await userEvent.type(screen.getByLabelText(/Current code or recovery code/), "12345");
      await userEvent.click(screen.getByRole("button", { name: /confirm turn off/i }));
      expect(await screen.findByRole("alert")).toHaveTextContent(/authenticator code or an unused recovery code/i);
      expect(client.mfaDisable).not.toHaveBeenCalled();
    });
  });
});


describe("SecondFactorField", () => {
  it("takes an authenticator code or a recovery code, and drops anything else", async () => {
    const seen: string[] = [];
    function Harness() {
      const [value, setValue] = React.useState("");
      return (
        <SecondFactorField
          value={value}
          onChange={(next) => {
            seen.push(next);
            setValue(next);
          }}
        />
      );
    }
    render(<Harness />);
    const input = screen.getByLabelText(/Verification code or recovery code/);
    expect(input).toHaveAttribute("name", "mfa_code");
    expect(input).toHaveAttribute("autocomplete", "one-time-code");
    // A numeric keypad would make a recovery code impossible to type.
    expect(input).not.toHaveAttribute("inputmode", "numeric");

    await userEvent.type(input, "ab!c<d>-12 3");
    expect(input).toHaveValue("abcd-12 3");
    expect(screen.getByText(/lost the device, use one of your recovery codes/i)).toBeInTheDocument();
  });
});
