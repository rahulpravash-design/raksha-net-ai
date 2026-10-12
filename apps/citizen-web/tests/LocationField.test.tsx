import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  EMPTY_LOCATION,
  LocationField,
  type LocationValue,
} from "@/components/LocationField";

function mockGeolocation(
  implementation: (
    success: PositionCallback,
    failure: PositionErrorCallback,
  ) => void,
) {
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: { getCurrentPosition: implementation },
  });
}

function position(latitude: number, longitude: number, accuracy: number) {
  return {
    coords: { latitude, longitude, accuracy },
  } as GeolocationPosition;
}

/** Matches the numeric codes in the spec, which jsdom does not provide. */
const ERROR_CODES = {
  PERMISSION_DENIED: 1,
  POSITION_UNAVAILABLE: 2,
  TIMEOUT: 3,
} as const;

function geolocationError(code: number) {
  return { code, ...ERROR_CODES } as unknown as GeolocationPositionError;
}

describe("LocationField", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("captures a device fix and reports it upwards", async () => {
    mockGeolocation((success) => success(position(13.0827, 80.2707, 12)));
    const onChange = vi.fn();

    render(<LocationField value={EMPTY_LOCATION} onChange={onChange} />);
    await userEvent.click(
      screen.getByRole("button", { name: /use my current location/i }),
    );

    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({
        latitude: 13.0827,
        longitude: 80.2707,
        accuracyMetres: 12,
        source: "device",
      }),
    );
  });

  it("explains a refused permission and keeps manual entry available", async () => {
    mockGeolocation((_success, failure) =>
      failure(geolocationError(ERROR_CODES.PERMISSION_DENIED)),
    );

    render(<LocationField value={EMPTY_LOCATION} onChange={vi.fn()} />);
    await userEvent.click(
      screen.getByRole("button", { name: /use my current location/i }),
    );

    expect(await screen.findByRole("status")).toHaveTextContent(
      /permission was refused/i,
    );
    expect(screen.getByLabelText(/latitude/i)).toBeEnabled();
  });

  it("explains a timeout differently from a refusal", async () => {
    mockGeolocation((_success, failure) =>
      failure(geolocationError(ERROR_CODES.TIMEOUT)),
    );

    render(<LocationField value={EMPTY_LOCATION} onChange={vi.fn()} />);
    await userEvent.click(
      screen.getByRole("button", { name: /use my current location/i }),
    );

    expect(await screen.findByRole("status")).toHaveTextContent(/took too long/i);
  });

  it("warns when a fix is too vague to send a crew to unaided", () => {
    const vague: LocationValue = {
      latitude: 13.0827,
      longitude: 80.2707,
      accuracyMetres: 850,
      source: "device",
    };

    render(<LocationField value={vague} onChange={vi.fn()} />);

    expect(screen.getByText(/please add a landmark/i)).toBeInTheDocument();
  });

  it("does not warn about a precise fix", () => {
    const precise: LocationValue = {
      latitude: 13.0827,
      longitude: 80.2707,
      accuracyMetres: 8,
      source: "device",
    };

    render(<LocationField value={precise} onChange={vi.fn()} />);

    expect(screen.queryByText(/please add a landmark/i)).not.toBeInTheDocument();
    expect(screen.getByText(/accurate to about 8 m/i)).toBeInTheDocument();
  });

  it("accepts coordinates typed by hand", async () => {
    const onChange = vi.fn();
    render(<LocationField value={EMPTY_LOCATION} onChange={onChange} />);

    await userEvent.type(screen.getByLabelText(/latitude/i), "13.08");

    expect(onChange).toHaveBeenCalled();
    const last = onChange.mock.lastCall![0] as LocationValue;
    expect(last.source).toBe("manual");
  });

  it("ignores text that is not a number", async () => {
    const onChange = vi.fn();
    render(<LocationField value={EMPTY_LOCATION} onChange={onChange} />);

    await userEvent.type(screen.getByLabelText(/latitude/i), "north");

    const last = onChange.mock.lastCall![0] as LocationValue;
    expect(last.latitude).toBeNull();
  });
});
