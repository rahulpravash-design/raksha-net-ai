"use client";

import { useCallback, useState } from "react";

import { formatCoordinates } from "@raksha/api-client";

import { MAP_DEFAULTS } from "@/lib/config";
import { Button, Field, TextInput } from "./ui";

export interface LocationValue {
  latitude: number | null;
  longitude: number | null;
  accuracyMetres: number | null;
  /** How the coordinates were obtained, shown to the operator later. */
  source: "device" | "manual" | null;
}

export const EMPTY_LOCATION: LocationValue = {
  latitude: null,
  longitude: null,
  accuracyMetres: null,
  source: null,
};

/** Above this, a device fix is too vague to send a crew to unaided. */
const POOR_ACCURACY_METRES = 100;

function geolocationMessage(error: GeolocationPositionError): string {
  switch (error.code) {
    case error.PERMISSION_DENIED:
      return "Location permission was refused. Enter the coordinates below, or describe the place as precisely as you can.";
    case error.POSITION_UNAVAILABLE:
      return "Your device could not get a position fix. Enter the coordinates below if you know them.";
    case error.TIMEOUT:
      return "Getting your location took too long. Try again, or enter it below.";
    default:
      return "Your location could not be read. Enter it below instead.";
  }
}

/**
 * Location capture.
 *
 * Browser geolocation is offered first because it is fastest, but it is never
 * the only path: permission can be refused and a fix can be wrong, so manual
 * entry is always available and the reported accuracy is always shown.
 */
export function LocationField({
  value,
  onChange,
  disabled,
}: {
  value: LocationValue;
  onChange: (value: LocationValue) => void;
  disabled?: boolean;
}) {
  const [locating, setLocating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const useDeviceLocation = useCallback(() => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setMessage("This browser cannot share a location. Enter it below.");
      return;
    }

    setLocating(true);
    setMessage(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        onChange({
          latitude: Number(position.coords.latitude.toFixed(6)),
          longitude: Number(position.coords.longitude.toFixed(6)),
          accuracyMetres: position.coords.accuracy
            ? Math.round(position.coords.accuracy)
            : null,
          source: "device",
        });
        setLocating(false);
      },
      (error) => {
        setMessage(geolocationMessage(error));
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 0 },
    );
  }, [onChange]);

  function updateCoordinate(key: "latitude" | "longitude", raw: string) {
    const parsed = raw.trim() === "" ? null : Number(raw);
    onChange({
      ...value,
      [key]: parsed !== null && Number.isFinite(parsed) ? parsed : null,
      source: "manual",
      accuracyMetres: null,
    });
  }

  const hasFix = value.latitude !== null && value.longitude !== null;
  const poorAccuracy =
    value.accuracyMetres !== null && value.accuracyMetres > POOR_ACCURACY_METRES;

  return (
    <fieldset className="surface space-y-3 rounded-xl p-4" disabled={disabled}>
      <legend className="px-1 text-sm font-semibold">Location</legend>

      <Button
        type="button"
        variant="secondary"
        loading={locating}
        onClick={useDeviceLocation}
        className="w-full"
      >
        {locating ? "Getting your location" : "Use my current location"}
      </Button>

      {message && (
        <p role="status" className="text-sm text-amber-700 dark:text-amber-300">
          {message}
        </p>
      )}

      {hasFix && (
        <div className="rounded-lg bg-brand-50 px-3 py-2 text-sm dark:bg-brand-900/30">
          <p className="font-medium">
            {formatCoordinates(value.latitude!, value.longitude!)}
          </p>
          {value.accuracyMetres !== null && (
            <p className={poorAccuracy ? "text-amber-700 dark:text-amber-300" : "muted"}>
              Accurate to about {value.accuracyMetres} m
              {poorAccuracy
                ? " — please add a landmark below so the crew can find you."
                : ""}
            </p>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Field label="Latitude" hint={`e.g. ${MAP_DEFAULTS.centre.latitude}`}>
          <TextInput
            inputMode="decimal"
            name="latitude"
            value={value.latitude ?? ""}
            onChange={(event) => updateCoordinate("latitude", event.target.value)}
          />
        </Field>
        <Field label="Longitude" hint={`e.g. ${MAP_DEFAULTS.centre.longitude}`}>
          <TextInput
            inputMode="decimal"
            name="longitude"
            value={value.longitude ?? ""}
            onChange={(event) => updateCoordinate("longitude", event.target.value)}
          />
        </Field>
      </div>
    </fieldset>
  );
}
