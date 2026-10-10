"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  canDispatch,
  isAdminRole,
  type Hospital,
} from "@raksha/api-client";

import { useAuth } from "@/components/AuthProvider";
import { HospitalCard } from "@/components/hospitals/HospitalCard";
import { HospitalRegisterForm } from "@/components/hospitals/HospitalRegisterForm";
import { HospitalDetail } from "@/components/hospitals/HospitalDetail";
import {
  Button,
  EmptyState,
  ErrorBanner,
  Spinner,
  TextInput,
} from "@/components/ui";
import { getApiClient } from "@/lib/api";

const REFRESH_MS = 30_000;

export default function HospitalsPage() {
  const router = useRouter();
  const api = getApiClient();
  const { user, loading: authLoading } = useAuth();

  const [hospitals, setHospitals] = useState<Hospital[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [onlyAccepting, setOnlyAccepting] = useState(false);
  const [registering, setRegistering] = useState(false);

  const load = useCallback(async () => {
    try {
      const page = await api.hospitals({ page_size: 100, active_only: true });
      setHospitals(page.items);
      setError(null);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) return;
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Hospitals could not be loaded.",
      );
    }
  }, [api]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    // Session token is in browser storage; every setState follows an await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    const timer = setInterval(() => void load(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [authLoading, user, router, load]);

  const mayDispatch = user ? canDispatch(user.role) : false;
  const isAdmin = user ? isAdminRole(user.role) : false;
  const isMine = useCallback(
    (hospital: Hospital) => !!user && hospital.managed_by?.id === user.id,
    [user],
  );

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (hospitals ?? [])
      .filter((h) => !onlyAccepting || h.accepting_emergencies)
      .filter(
        (h) =>
          !needle ||
          h.name.toLowerCase().includes(needle) ||
          h.code.toLowerCase().includes(needle),
      )
      .sort(
        (a, b) =>
          Number(isMine(b)) - Number(isMine(a)) || a.name.localeCompare(b.name),
      );
  }, [hospitals, search, onlyAccepting, isMine]);

  const selected = hospitals?.find((h) => h.id === selectedId) ?? null;

  if (authLoading || (!hospitals && !error))
    return <Spinner label="Loading hospitals" />;
  if (!user) return null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold tracking-wide">HOSPITALS</h1>
          <p className="muted text-xs">
            Capacity as last reported by each hospital — figures are entered by
            hand and may lag reality. Dispatchers choose where to send patients;
            this screen informs that choice.
          </p>
        </div>
        {isAdmin && !registering && (
          <Button onClick={() => setRegistering(true)}>
            Register a hospital
          </Button>
        )}
      </div>

      {registering && (
        <section className="panel-3d rounded-xl p-4">
          <h2 className="mb-3 font-semibold">Register a hospital</h2>
          <HospitalRegisterForm
            onCancel={() => setRegistering(false)}
            onCreated={(created) => {
              setRegistering(false);
              setSelectedId(created.id);
              void load();
            }}
          />
        </section>
      )}

      <ErrorBanner message={error} />

      <div className="panel-3d grid gap-2 rounded-xl p-3 sm:grid-cols-[1fr_auto]">
        <TextInput
          type="search"
          aria-label="Search hospitals"
          placeholder="Search name or code"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <label className="flex items-center gap-2 px-2 text-sm">
          <input
            type="checkbox"
            checked={onlyAccepting}
            onChange={(e) => setOnlyAccepting(e.target.checked)}
          />
          Only those accepting emergencies
        </label>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_28rem]">
        {visible.length === 0 ? (
          <EmptyState
            title="No hospitals to show"
            body={
              hospitals && hospitals.length === 0
                ? "No hospitals are registered. An administrator registers them."
                : "Try clearing a filter."
            }
          />
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2" aria-label="Hospitals">
            {visible.map((hospital, index) => (
              <HospitalCard
                key={hospital.id}
                hospital={hospital}
                index={index}
                mine={isMine(hospital)}
                selected={hospital.id === selectedId}
                onSelect={() => setSelectedId(hospital.id)}
              />
            ))}
          </ul>
        )}

        <div>
          {selected ? (
            <HospitalDetail
              key={selected.id}
              hospital={selected}
              canSeeNotices={mayDispatch || isMine(selected)}
              canReportCapacity={mayDispatch || isMine(selected)}
              noticeViewer={mayDispatch ? "dispatch" : "hospital"}
              onChanged={() => void load()}
            />
          ) : (
            <p className="panel-3d muted rounded-xl p-4 text-sm">
              Select a hospital to see its detail.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
