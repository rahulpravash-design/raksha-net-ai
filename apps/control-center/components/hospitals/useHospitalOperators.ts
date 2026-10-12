"use client";

import { useEffect, useState } from "react";

import type { AdminUser } from "@raksha/api-client";

import { getApiClient } from "@/lib/api";

/** Active hospital-operator accounts, for choosing who maintains a hospital. */
export function useHospitalOperators(): AdminUser[] {
  const [operators, setOperators] = useState<AdminUser[]>([]);
  useEffect(() => {
    let cancelled = false;
    getApiClient()
      .adminUsers({ role: "HOSPITAL_OPERATOR", is_active: true, page_size: 100 })
      .then((page) => {
        if (!cancelled) setOperators(page.items);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  return operators;
}
