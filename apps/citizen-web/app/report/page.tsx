"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import {
  ApiError,
  INCIDENT_CATEGORIES,
  categoryLabel,
  type IncidentCategory,
} from "@raksha/api-client";

import { useAuth } from "@/components/AuthProvider";
import {
  EMPTY_LOCATION,
  LocationField,
  type LocationValue,
} from "@/components/LocationField";
import { Button, ErrorBanner, Field, Spinner, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";

const MIN_DESCRIPTION = 10;
const MAX_DESCRIPTION = 4000;
const MAX_PHOTOS = 4;

export default function ReportPage() {
  const router = useRouter();
  const api = getApiClient();
  const { user, loading } = useAuth();

  const [category, setCategory] = useState<IncidentCategory>("FLOOD");
  const [description, setDescription] = useState("");
  const [location, setLocation] = useState<LocationValue>(EMPTY_LOCATION);
  const [landmark, setLandmark] = useState("");
  const [addressText, setAddressText] = useState("");
  const [peopleAffected, setPeopleAffected] = useState("");
  const [peopleTrapped, setPeopleTrapped] = useState(false);
  const [medicalRequired, setMedicalRequired] = useState(false);
  const [immediateDanger, setImmediateDanger] = useState(false);
  const [photos, setPhotos] = useState<File[]>([]);

  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading) return <Spinner label="Checking your session" />;
  if (!user) return null;

  function validate(): boolean {
    const problems: Record<string, string> = {};
    if (description.trim().length < MIN_DESCRIPTION) {
      problems.description = `Please describe the emergency in at least ${MIN_DESCRIPTION} characters.`;
    }
    if (location.latitude === null || location.longitude === null) {
      problems.location =
        "A location is required so responders know where to go.";
    }
    setFieldErrors(problems);
    return Object.keys(problems).length === 0;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!validate()) return;

    setSubmitting(true);
    setProgress("Sending your report…");
    try {
      const incident = await api.createIncident({
        category,
        description: description.trim(),
        latitude: location.latitude!,
        longitude: location.longitude!,
        location_accuracy_m: location.accuracyMetres,
        address_text: addressText.trim() || null,
        landmark: landmark.trim() || null,
        people_affected: peopleAffected === "" ? null : Number(peopleAffected),
        people_trapped: peopleTrapped,
        medical_required: medicalRequired,
        immediate_danger: immediateDanger,
      });

      // The report is already filed at this point. A photograph that fails to
      // upload must not lose it, so failures here are reported, not fatal.
      const failed: string[] = [];
      for (const [index, photo] of photos.entries()) {
        setProgress(`Uploading photo ${index + 1} of ${photos.length}…`);
        try {
          await api.uploadMedia(incident.id, photo);
        } catch {
          failed.push(photo.name);
        }
      }

      const query = failed.length > 0 ? "?media_failed=1" : "";
      router.push(`/reports/${incident.id}${query}`);
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFieldErrors(caught.fieldErrors);
      } else {
        setError(
          "Your report could not be sent. Check your connection and try again — if this is life-threatening, call your emergency number now.",
        );
      }
      setSubmitting(false);
      setProgress(null);
    }
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold">Report an emergency</h1>
        <p className="muted text-sm">
          Tell us what is happening and where. You can add photographs at the end.
        </p>
      </header>

      <form onSubmit={handleSubmit} className="space-y-5" noValidate>
        <ErrorBanner message={error} />

        <Field label="What is happening?" required>
          <select
            name="category"
            className="surface w-full rounded-lg px-3 py-2.5 text-sm"
            value={category}
            onChange={(event) =>
              setCategory(event.target.value as IncidentCategory)
            }
          >
            {INCIDENT_CATEGORIES.map((value) => (
              <option key={value} value={value}>
                {categoryLabel(value)}
              </option>
            ))}
          </select>
        </Field>

        <Field
          label="Describe the situation"
          required
          hint="In your own words. Mention anything a crew should know before arriving."
          error={fieldErrors.description}
        >
          <textarea
            name="description"
            rows={5}
            required
            minLength={MIN_DESCRIPTION}
            maxLength={MAX_DESCRIPTION}
            className="surface w-full rounded-lg px-3 py-2.5 text-sm"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>

        <div className="space-y-1">
          <LocationField
            value={location}
            onChange={setLocation}
            disabled={submitting}
          />
          {fieldErrors.location && (
            <p role="alert" className="text-xs font-medium text-red-600">
              {fieldErrors.location}
            </p>
          )}
        </div>

        <Field label="Nearest landmark" hint="Optional. Helps a crew find the spot.">
          <TextInput
            name="landmark"
            value={landmark}
            onChange={(event) => setLandmark(event.target.value)}
          />
        </Field>

        <Field label="Street or area" hint="Optional.">
          <TextInput
            name="address_text"
            value={addressText}
            onChange={(event) => setAddressText(event.target.value)}
          />
        </Field>

        <fieldset className="surface space-y-3 rounded-xl p-4">
          <legend className="px-1 text-sm font-semibold">
            Who is affected
          </legend>

          <Field
            label="How many people are affected?"
            hint="Your best estimate is fine. Leave blank if you cannot tell."
            error={fieldErrors.people_affected}
          >
            <TextInput
              type="number"
              inputMode="numeric"
              min={0}
              name="people_affected"
              value={peopleAffected}
              onChange={(event) => setPeopleAffected(event.target.value)}
            />
          </Field>

          {[
            {
              id: "people_trapped",
              label: "People are trapped",
              checked: peopleTrapped,
              set: setPeopleTrapped,
            },
            {
              id: "medical_required",
              label: "Someone needs medical help",
              checked: medicalRequired,
              set: setMedicalRequired,
            },
            {
              id: "immediate_danger",
              label: "There is immediate danger to life",
              checked: immediateDanger,
              set: setImmediateDanger,
            },
          ].map((item) => (
            <label key={item.id} className="flex items-center gap-3 text-sm">
              <input
                type="checkbox"
                name={item.id}
                className="h-5 w-5 rounded"
                checked={item.checked}
                onChange={(event) => item.set(event.target.checked)}
              />
              {item.label}
            </label>
          ))}
        </fieldset>

        <Field
          label="Photographs"
          hint={`Optional. Up to ${MAX_PHOTOS} images, 10 MB each.`}
        >
          <input
            type="file"
            name="photos"
            accept="image/jpeg,image/png,image/webp"
            multiple
            className="block w-full text-sm"
            onChange={(event) =>
              setPhotos(Array.from(event.target.files ?? []).slice(0, MAX_PHOTOS))
            }
          />
        </Field>

        <div className="space-y-2">
          <Button
            type="submit"
            variant="danger"
            loading={submitting}
            className="w-full py-3 text-base"
          >
            Submit report
          </Button>
          {progress && (
            <p role="status" className="muted text-center text-sm">
              {progress}
            </p>
          )}
        </div>
      </form>
    </div>
  );
}
