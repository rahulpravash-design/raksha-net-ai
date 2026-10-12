/**
 * The HTTP client every RAKSHA NET AI front end uses.
 *
 * Responsibilities kept here on purpose:
 *  - one place that knows the error envelope, so the UI never parses raw JSON;
 *  - transparent access-token refresh, with concurrent calls sharing one
 *    refresh rather than each racing to rotate the token (a race would trip the
 *    backend's reuse detection and log the user out).
 */

import type { ApiConfigProblem } from "./config";
import type {
  AnalysisReviewInput,
  AdminUser,
  AnalyticsQuery,
  ApiErrorBody,
  CategoryBreakdown,
  Hotspots,
  ResourceUtilization,
  TimeStats,
  CreateUserInput,
  MfaEnabled,
  MfaEnrollment,
  MfaRecoveryStatus,
  UpdateUserInput,
  UserRole,
  UserSummary,
  AppNotification,
  Dispatch,
  DispatchStatus,
  CreateIncidentInput,
  GeoFeatureCollection,
  Incident,
  IncidentAnalysis,
  IncidentQuery,
  IncidentStats,
  IncidentStatus,
  IncidentSummary,
  MediaItem,
  NearbyResource,
  Page,
  PriorityBand,
  Resource,
  CreateHospitalInput,
  CreateHospitalNoticeInput,
  UpdateHospitalInput,
  CreateResourceInput,
  Hospital,
  HospitalCapacityInput,
  HospitalNotice,
  HospitalNoticeStatus,
  NearbyHospital,
  ResourceRecommendations,
  ResourceStats,
  UpdateResourceInput,
  ResourceStatus,
  ResourceType,
  ResponderAssignment,
  StatusHistoryEntry,
  TokenResponse,
  User,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly requestId: string | undefined;

  constructor(status: number, body: Partial<ApiErrorBody["error"]> = {}) {
    super(body.message ?? "The request could not be completed.");
    this.name = "ApiError";
    this.status = status;
    this.code = body.code ?? "UNKNOWN_ERROR";
    this.details = body.details ?? {};
    this.requestId = body.request_id;
  }

  /** True when re-sending the same request could plausibly succeed. */
  get isRetryable(): boolean {
    return this.status === 429 || this.status >= 500;
  }

  /** Field-level messages from a validation failure, for form display. */
  get fieldErrors(): Record<string, string> {
    const fields = this.details.fields;
    if (!Array.isArray(fields)) return {};
    const result: Record<string, string> = {};
    for (const entry of fields) {
      if (
        entry &&
        typeof entry === "object" &&
        "field" in entry &&
        "message" in entry
      ) {
        result[String(entry.field)] = String(entry.message);
      }
    }
    return result;
  }
}

/**
 * Raised, before any network call, when the front end was built without a usable API
 * address (see `config.ts`). It is an `ApiError` on purpose: every screen already shows
 * an `ApiError`'s message, so each one reports the misconfiguration instead of falling
 * back to "Could not reach the server". Status 0 because no response exists.
 */
export class ApiConfigurationError extends ApiError {
  readonly problem: ApiConfigProblem;

  constructor(problem: ApiConfigProblem) {
    super(0, {
      code: "API_NOT_CONFIGURED",
      message: problem.message,
      details: { reason: problem.code },
    });
    this.name = "ApiConfigurationError";
    this.problem = problem;
  }
}

export interface TokenStore {
  getAccessToken(): string | null;
  getRefreshToken(): string | null;
  setTokens(tokens: { access: string; refresh: string }): void;
  clear(): void;
}

export interface ApiClientOptions {
  baseUrl: string;
  /**
   * Set when the API address failed validation (`resolveApiConfig`). Every request then
   * throws an `ApiConfigurationError` without touching the network.
   */
  configProblem?: ApiConfigProblem;
  tokens?: TokenStore;
  /** Called when the session ends irrecoverably, so the UI can redirect. */
  onUnauthenticated?: () => void;
  /**
   * Called when the backend says this account must set up two-factor
   * authentication before it can do anything else, so the UI can send the user
   * to the enrolment screen instead of showing a wall of failed requests.
   */
  onMfaEnrolmentRequired?: () => void;
  /**
   * Called when the backend says an administrator-set password must be changed
   * before anything else can be done, so the UI can send the user to do it.
   */
  onPasswordChangeRequired?: () => void;
  fetchImpl?: typeof fetch;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, unknown>;
  /** Skip the token refresh dance — used by the auth endpoints themselves. */
  anonymous?: boolean;
  signal?: AbortSignal;
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly configProblem: ApiConfigProblem | undefined;
  private readonly tokens: TokenStore | undefined;
  private readonly onUnauthenticated: (() => void) | undefined;
  private readonly onMfaEnrolmentRequired: (() => void) | undefined;
  private readonly onPasswordChangeRequired: (() => void) | undefined;
  private readonly fetchImpl: typeof fetch;
  /** Shared so simultaneous 401s trigger exactly one token rotation. */
  private refreshInFlight: Promise<boolean> | null = null;

  constructor(options: ApiClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.configProblem = options.configProblem;
    this.tokens = options.tokens;
    this.onUnauthenticated = options.onUnauthenticated;
    this.onMfaEnrolmentRequired = options.onMfaEnrolmentRequired;
    this.onPasswordChangeRequired = options.onPasswordChangeRequired;
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  // --- authentication ------------------------------------------------------
  async register(input: {
    email: string;
    password: string;
    full_name: string;
    phone?: string | null;
  }): Promise<User> {
    return this.request<User>("/api/v1/auth/register", {
      method: "POST",
      body: input,
      anonymous: true,
    });
  }

  async login(
    email: string,
    password: string,
    mfaCode?: string,
  ): Promise<TokenResponse> {
    const tokens = await this.request<TokenResponse>("/api/v1/auth/login", {
      method: "POST",
      body: mfaCode
        ? { email, password, mfa_code: mfaCode }
        : { email, password },
      anonymous: true,
    });
    this.tokens?.setTokens({
      access: tokens.access_token,
      refresh: tokens.refresh_token,
    });
    return tokens;
  }

  async logout(): Promise<void> {
    const refresh = this.tokens?.getRefreshToken();
    if (refresh) {
      try {
        await this.request("/api/v1/auth/logout", {
          method: "POST",
          body: { refresh_token: refresh },
          anonymous: true,
        });
      } catch {
        // Signing out locally must succeed even if the server call does not.
      }
    }
    this.tokens?.clear();
  }

  async me(): Promise<User> {
    return this.request<User>("/api/v1/auth/me");
  }

  // --- analytics (DISPATCH roles) --------------------------------------------
  async responseTime(query: AnalyticsQuery = {}): Promise<TimeStats> {
    return this.request<TimeStats>("/api/v1/analytics/response-time", { query: { ...query } });
  }

  async resolutionTime(query: AnalyticsQuery = {}): Promise<TimeStats> {
    return this.request<TimeStats>("/api/v1/analytics/resolution-time", { query: { ...query } });
  }

  async categoryBreakdown(query: Pick<AnalyticsQuery, "since" | "until"> = {}): Promise<CategoryBreakdown> {
    return this.request<CategoryBreakdown>("/api/v1/analytics/category-breakdown", {
      query: { ...query },
    });
  }

  async resourceUtilization(query: Pick<AnalyticsQuery, "since" | "until"> = {}): Promise<ResourceUtilization> {
    return this.request<ResourceUtilization>("/api/v1/analytics/resource-utilization", {
      query: { ...query },
    });
  }

  async hotspots(query: AnalyticsQuery & { limit?: number } = {}): Promise<Hotspots> {
    return this.request<Hotspots>("/api/v1/analytics/hotspots", { query: { ...query } });
  }

  // --- password recovery (no session needed) ---------------------------------
  /** Whether this deployment can send recovery email at all. */
  async recoveryStatus(): Promise<{ email_available: boolean }> {
    return this.request<{ email_available: boolean }>("/api/v1/auth/recovery-status", {
      anonymous: true,
    });
  }

  /** Always resolves the same way for any address; the answer reveals nothing about accounts. */
  async requestPasswordReset(email: string): Promise<void> {
    await this.request<{ message: string }>("/api/v1/auth/forgot-password", {
      method: "POST",
      body: { email },
      anonymous: true,
    });
  }

  /** Spend a recovery link. Does not sign anyone in. */
  async resetPassword(token: string, newPassword: string): Promise<void> {
    await this.request<{ message: string }>("/api/v1/auth/reset-password", {
      method: "POST",
      body: { token, new_password: newPassword },
      anonymous: true,
    });
  }

  // --- password ---------------------------------------------------------------
  /**
   * Replace your own password. Every other session is ended; the response carries
   * fresh tokens, which are stored so this session continues.
   */
  async changePassword(
    currentPassword: string,
    newPassword: string,
    mfaCode?: string,
  ): Promise<TokenResponse> {
    const tokens = await this.request<TokenResponse>("/api/v1/auth/password", {
      method: "POST",
      body: {
        current_password: currentPassword,
        new_password: newPassword,
        ...(mfaCode ? { mfa_code: mfaCode } : {}),
      },
    });
    this.tokens?.setTokens({ access: tokens.access_token, refresh: tokens.refresh_token });
    return tokens;
  }

  /** Administrators: set a temporary password; the user must change it at first sign-in. */
  async adminResetPassword(id: string, newPassword: string): Promise<AdminUser> {
    return this.request<AdminUser>(`/api/v1/users/${id}/reset-password`, {
      method: "POST",
      body: { new_password: newPassword },
    });
  }

  // --- two-factor authentication -------------------------------------------
  async mfaEnroll(): Promise<MfaEnrollment> {
    return this.request<MfaEnrollment>("/api/v1/auth/mfa/enroll", { method: "POST" });
  }

  /** Confirm enrolment with an authenticator code. The response carries the recovery codes. */
  async mfaEnable(code: string): Promise<MfaEnabled> {
    return this.request<MfaEnabled>("/api/v1/auth/mfa/enable", { method: "POST", body: { code } });
  }

  async mfaRecoveryStatus(): Promise<MfaRecoveryStatus> {
    return this.request<MfaRecoveryStatus>("/api/v1/auth/mfa/recovery-codes");
  }

  /** Replace the whole set. `code` is an authenticator code or an unused recovery code. */
  async mfaRegenerateRecoveryCodes(password: string, code: string): Promise<string[]> {
    const result = await this.request<{ recovery_codes: string[] }>(
      "/api/v1/auth/mfa/recovery-codes",
      { method: "POST", body: { password, code } },
    );
    return result.recovery_codes;
  }

  /** `code` is an authenticator code, or a recovery code when the device is lost. */
  async mfaDisable(password: string, code: string): Promise<User> {
    return this.request<User>("/api/v1/auth/mfa/disable", {
      method: "POST",
      body: { password, code },
    });
  }

  // --- user administration (ADMIN, SUPER_ADMIN) -----------------------------
  async adminUsers(
    query: { page?: number; page_size?: number; role?: UserRole; is_active?: boolean; q?: string } = {},
  ): Promise<Page<AdminUser>> {
    return this.request<Page<AdminUser>>("/api/v1/users", { query: { ...query } });
  }

  async createUser(input: CreateUserInput): Promise<AdminUser> {
    return this.request<AdminUser>("/api/v1/users", { method: "POST", body: input });
  }

  async updateUser(id: string, changes: UpdateUserInput): Promise<AdminUser> {
    return this.request<AdminUser>(`/api/v1/users/${id}`, { method: "PATCH", body: changes });
  }

  async unlockUser(id: string): Promise<AdminUser> {
    return this.request<AdminUser>(`/api/v1/users/${id}/unlock`, { method: "POST" });
  }

  async resetUserMfa(id: string): Promise<AdminUser> {
    return this.request<AdminUser>(`/api/v1/users/${id}/reset-mfa`, { method: "POST" });
  }

  /** Active responders (id, name, role only) — for dispatchers linking a crew to a unit. */
  async responderDirectory(q?: string): Promise<UserSummary[]> {
    return this.request<UserSummary[]>("/api/v1/users/directory", {
      query: q ? { q } : {},
    });
  }

  // --- incidents -----------------------------------------------------------
  async createIncident(input: CreateIncidentInput): Promise<Incident> {
    return this.request<Incident>("/api/v1/incidents", {
      method: "POST",
      body: input,
    });
  }

  async myIncidents(query: IncidentQuery = {}): Promise<Page<IncidentSummary>> {
    return this.request<Page<IncidentSummary>>("/api/v1/incidents/mine", {
      query: { ...query },
    });
  }

  async incidentQueue(
    query: IncidentQuery = {},
  ): Promise<Page<IncidentSummary>> {
    return this.request<Page<IncidentSummary>>("/api/v1/incidents", {
      query: { ...query },
    });
  }

  async incident(id: string): Promise<Incident> {
    return this.request<Incident>(`/api/v1/incidents/${id}`);
  }

  async incidentHistory(id: string): Promise<StatusHistoryEntry[]> {
    return this.request<StatusHistoryEntry[]>(
      `/api/v1/incidents/${id}/history`,
    );
  }

  async incidentStats(): Promise<IncidentStats> {
    return this.request<IncidentStats>("/api/v1/incidents/stats/summary");
  }

  async changeStatus(
    id: string,
    status: IncidentStatus,
    note?: string,
    duplicateOfId?: string,
  ): Promise<Incident> {
    return this.request<Incident>(`/api/v1/incidents/${id}/status`, {
      method: "POST",
      body: {
        status,
        note: note ?? null,
        ...(duplicateOfId ? { duplicate_of_id: duplicateOfId } : {}),
      },
    });
  }

  async overridePriority(
    id: string,
    band: PriorityBand,
    reason: string,
  ): Promise<Incident> {
    return this.request<Incident>(`/api/v1/incidents/${id}/priority`, {
      method: "POST",
      body: { override_band: band, reason },
    });
  }

  async recalculatePriority(id: string): Promise<Incident> {
    return this.request<Incident>(`/api/v1/incidents/${id}/priority`, {
      method: "POST",
      body: {},
    });
  }

  async assignIncident(id: string, userId: string | null): Promise<Incident> {
    return this.request<Incident>(`/api/v1/incidents/${id}/assign`, {
      method: "POST",
      body: { assigned_to_id: userId },
    });
  }

  // --- AI analysis -----------------------------------------------------------
  /**
   * Ask the configured analyzer to propose structured facts from the
   * report's own description. Never changes the incident by itself — a
   * dispatcher must separately {@link reviewAnalysis} the result.
   */
  async runAnalysis(incidentId: string): Promise<IncidentAnalysis> {
    return this.request<IncidentAnalysis>(
      `/api/v1/incidents/${incidentId}/analyses`,
      {
        method: "POST",
      },
    );
  }

  async listAnalyses(incidentId: string): Promise<IncidentAnalysis[]> {
    return this.request<IncidentAnalysis[]>(
      `/api/v1/incidents/${incidentId}/analyses`,
    );
  }

  async reviewAnalysis(
    incidentId: string,
    analysisId: string,
    input: AnalysisReviewInput,
  ): Promise<IncidentAnalysis> {
    return this.request<IncidentAnalysis>(
      `/api/v1/incidents/${incidentId}/analyses/${analysisId}/review`,
      { method: "POST", body: input },
    );
  }

  // --- resources -------------------------------------------------------------
  async resources(
    query: {
      page?: number;
      page_size?: number;
      resource_type?: ResourceType[];
      status?: ResourceStatus[];
      active_only?: boolean;
      q?: string;
    } = {},
  ): Promise<Page<Resource>> {
    return this.request<Page<Resource>>("/api/v1/resources", {
      query: { ...query },
    });
  }

  async resourceStats(): Promise<ResourceStats> {
    return this.request<ResourceStats>("/api/v1/resources/stats/summary");
  }

  async createResource(input: CreateResourceInput): Promise<Resource> {
    return this.request<Resource>("/api/v1/resources", { method: "POST", body: input });
  }

  async updateResource(id: string, changes: UpdateResourceInput): Promise<Resource> {
    return this.request<Resource>(`/api/v1/resources/${id}`, {
      method: "PATCH",
      body: changes,
    });
  }

  async resource(id: string): Promise<Resource> {
    return this.request<Resource>(`/api/v1/resources/${id}`);
  }

  async resourcesNearby(params: {
    latitude: number;
    longitude: number;
    radius_km?: number;
    resource_type?: ResourceType[];
    available_only?: boolean;
    limit?: number;
  }): Promise<{ items: NearbyResource[]; count: number }> {
    return this.request<{ items: NearbyResource[]; count: number }>(
      "/api/v1/resources/nearby",
      { query: { ...params } },
    );
  }

  async setResourceStatus(
    id: string,
    status: ResourceStatus,
    position?: { latitude: number; longitude: number },
  ): Promise<Resource> {
    return this.request<Resource>(`/api/v1/resources/${id}/status`, {
      method: "POST",
      body: { status, ...(position ?? {}) },
    });
  }

  async resourceRecommendations(
    incidentId: string,
    limit = 10,
  ): Promise<ResourceRecommendations> {
    return this.request<ResourceRecommendations>(
      `/api/v1/incidents/${incidentId}/resource-recommendations`,
      { query: { limit } },
    );
  }

  // --- dispatch --------------------------------------------------------------
  /**
   * Send a unit. The approver recorded on the dispatch is the authenticated
   * caller — there is no field here to supply one.
   */
  async dispatchResource(
    incidentId: string,
    resourceId: string,
    note?: string,
  ): Promise<Dispatch> {
    return this.request<Dispatch>(
      `/api/v1/incidents/${incidentId}/dispatches`,
      {
        method: "POST",
        body: { resource_id: resourceId, note: note ?? null },
      },
    );
  }

  async incidentDispatches(incidentId: string): Promise<Dispatch[]> {
    return this.request<Dispatch[]>(
      `/api/v1/incidents/${incidentId}/dispatches`,
    );
  }

  // --- hospitals -------------------------------------------------------------
  async hospitals(
    query: { page?: number; page_size?: number; active_only?: boolean } = {},
  ): Promise<Page<Hospital>> {
    return this.request<Page<Hospital>>("/api/v1/hospitals", { query: { ...query } });
  }

  async createHospital(input: CreateHospitalInput): Promise<Hospital> {
    return this.request<Hospital>("/api/v1/hospitals", { method: "POST", body: input });
  }

  async updateHospital(id: string, input: UpdateHospitalInput): Promise<Hospital> {
    return this.request<Hospital>(`/api/v1/hospitals/${id}`, { method: "PATCH", body: input });
  }

  async hospitalsNearby(params: {
    latitude: number;
    longitude: number;
    radius_km?: number;
    accepting_only?: boolean;
    needs_icu?: boolean;
    limit?: number;
  }): Promise<{ items: NearbyHospital[]; count: number }> {
    return this.request<{ items: NearbyHospital[]; count: number }>(
      "/api/v1/hospitals/nearby",
      { query: { ...params } },
    );
  }

  async updateHospitalCapacity(id: string, input: HospitalCapacityInput): Promise<Hospital> {
    return this.request<Hospital>(`/api/v1/hospitals/${id}/capacity`, {
      method: "POST",
      body: input,
    });
  }

  async hospitalNotices(hospitalId: string, openOnly = true): Promise<HospitalNotice[]> {
    return this.request<HospitalNotice[]>(`/api/v1/hospitals/${hospitalId}/notices`, {
      query: { open_only: openOnly },
    });
  }

  async incidentHospitalNotices(incidentId: string): Promise<HospitalNotice[]> {
    return this.request<HospitalNotice[]>(`/api/v1/incidents/${incidentId}/hospital-notices`);
  }

  async createHospitalNotice(
    incidentId: string,
    input: CreateHospitalNoticeInput,
  ): Promise<HospitalNotice> {
    return this.request<HospitalNotice>(`/api/v1/incidents/${incidentId}/hospital-notices`, {
      method: "POST",
      body: input,
    });
  }

  async respondToHospitalNotice(
    id: string,
    status: HospitalNoticeStatus,
    responseNote?: string,
  ): Promise<HospitalNotice> {
    return this.request<HospitalNotice>(`/api/v1/hospital-notices/${id}/status`, {
      method: "POST",
      body: { status, response_note: responseNote ?? null },
    });
  }

  // --- notifications ---------------------------------------------------------
  async notifications(
    query: { page?: number; page_size?: number; unread_only?: boolean } = {},
  ): Promise<Page<AppNotification>> {
    return this.request<Page<AppNotification>>("/api/v1/notifications", {
      query: { ...query },
    });
  }

  async unreadNotificationCount(): Promise<number> {
    const body = await this.request<{ unread: number }>(
      "/api/v1/notifications/unread-count",
    );
    return body.unread;
  }

  async markNotificationRead(id: string): Promise<AppNotification> {
    return this.request<AppNotification>(`/api/v1/notifications/${id}/read`, {
      method: "POST",
    });
  }

  async markAllNotificationsRead(): Promise<void> {
    await this.request<{ message: string }>("/api/v1/notifications/read-all", {
      method: "POST",
    });
  }

  async myAssignments(openOnly = true): Promise<ResponderAssignment[]> {
    return this.request<ResponderAssignment[]>("/api/v1/dispatches/mine", {
      query: { open_only: openOnly },
    });
  }

  async dispatch(id: string): Promise<ResponderAssignment> {
    return this.request<ResponderAssignment>(`/api/v1/dispatches/${id}`);
  }

  async setDispatchStatus(
    id: string,
    status: DispatchStatus,
    options: { note?: string; reason?: string } = {},
  ): Promise<ResponderAssignment> {
    return this.request<ResponderAssignment>(
      `/api/v1/dispatches/${id}/status`,
      {
        method: "POST",
        body: {
          status,
          note: options.note ?? null,
          reason: options.reason ?? null,
        },
      },
    );
  }

  // --- media ---------------------------------------------------------------
  async uploadMedia(incidentId: string, file: File): Promise<MediaItem> {
    const form = new FormData();
    form.append("file", file);
    return this.requestRaw<MediaItem>(`/api/v1/incidents/${incidentId}/media`, {
      method: "POST",
      body: form,
    });
  }

  /** The URL an authenticated client can fetch the bytes from. */
  mediaContentUrl(mediaId: string): string {
    if (this.configProblem) throw new ApiConfigurationError(this.configProblem);
    return `${this.baseUrl}/api/v1/media/${mediaId}/content`;
  }

  /**
   * Media is behind authentication, so an `<img src>` cannot fetch it directly.
   * The caller is responsible for revoking the returned object URL.
   */
  async mediaObjectUrl(mediaId: string): Promise<string> {
    const response = await this.authorisedFetch(
      this.mediaContentUrl(mediaId),
      {},
    );
    if (!response.ok) throw await this.toError(response);
    return URL.createObjectURL(await response.blob());
  }

  // --- geo -----------------------------------------------------------------
  async incidentsInViewport(bounds: {
    minLat: number;
    minLon: number;
    maxLat: number;
    maxLon: number;
    openOnly?: boolean;
  }): Promise<GeoFeatureCollection> {
    return this.request<GeoFeatureCollection>("/api/v1/geo/incidents/bbox", {
      query: {
        min_lat: bounds.minLat,
        min_lon: bounds.minLon,
        max_lat: bounds.maxLat,
        max_lon: bounds.maxLon,
        open_only: bounds.openOnly ?? true,
      },
    });
  }

  async health(): Promise<{ status: string; version: string }> {
    return this.request("/api/v1/health", { anonymous: true });
  }

  // --- internals -----------------------------------------------------------
  /** Every request builds its URL first, so this is the one place that refuses. */
  private buildUrl(path: string, query?: Record<string, unknown>): string {
    if (this.configProblem) throw new ApiConfigurationError(this.configProblem);
    const url = new URL(`${this.baseUrl}${path}`);
    for (const [key, value] of Object.entries(query ?? {})) {
      if (value === undefined || value === null || value === "") continue;
      if (Array.isArray(value)) {
        for (const item of value) url.searchParams.append(key, String(item));
      } else {
        url.searchParams.set(key, String(value));
      }
    }
    return url.toString();
  }

  private async request<T>(
    path: string,
    options: RequestOptions = {},
  ): Promise<T> {
    const init: RequestInit = { method: options.method ?? "GET" };
    if (options.signal) init.signal = options.signal;
    if (options.body !== undefined) {
      init.headers = { "Content-Type": "application/json" };
      init.body = JSON.stringify(options.body);
    }

    const url = this.buildUrl(path, options.query);
    const response = options.anonymous
      ? await this.fetchImpl(url, init)
      : await this.authorisedFetch(url, init);

    if (!response.ok) throw await this.failure(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  private async requestRaw<T>(path: string, init: RequestInit): Promise<T> {
    const response = await this.authorisedFetch(this.buildUrl(path), init);
    if (!response.ok) throw await this.failure(response);
    return (await response.json()) as T;
  }

  private async failure(response: Response): Promise<ApiError> {
    const error = await this.toError(response);
    if (error.code === "MFA_ENROLLMENT_REQUIRED") this.onMfaEnrolmentRequired?.();
    if (error.code === "PASSWORD_CHANGE_REQUIRED") this.onPasswordChangeRequired?.();
    return error;
  }

  /** Send with the access token, refreshing once on a 401. */
  private async authorisedFetch(
    url: string,
    init: RequestInit,
  ): Promise<Response> {
    const first = await this.fetchImpl(url, this.withAuth(init));
    if (first.status !== 401) return first;

    const refreshed = await this.refreshOnce();
    if (!refreshed) {
      this.tokens?.clear();
      this.onUnauthenticated?.();
      return first;
    }
    return this.fetchImpl(url, this.withAuth(init));
  }

  private withAuth(init: RequestInit): RequestInit {
    const token = this.tokens?.getAccessToken();
    if (!token) return init;
    return {
      ...init,
      headers: { ...(init.headers ?? {}), Authorization: `Bearer ${token}` },
    };
  }

  /**
   * Rotate the refresh token, at most once at a time.
   *
   * Without this guard, several parallel requests hitting a just-expired access
   * token would each present the same refresh token. The backend treats the
   * second presentation as replay of a revoked credential and ends every
   * session — so the shared promise is a correctness requirement, not an
   * optimisation.
   */
  private async refreshOnce(): Promise<boolean> {
    if (this.refreshInFlight) return this.refreshInFlight;

    const refreshToken = this.tokens?.getRefreshToken();
    if (!refreshToken) return false;

    this.refreshInFlight = (async () => {
      try {
        const response = await this.fetchImpl(
          this.buildUrl("/api/v1/auth/refresh"),
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: refreshToken }),
          },
        );
        if (!response.ok) return false;
        const tokens = (await response.json()) as TokenResponse;
        this.tokens?.setTokens({
          access: tokens.access_token,
          refresh: tokens.refresh_token,
        });
        return true;
      } catch {
        return false;
      } finally {
        this.refreshInFlight = null;
      }
    })();

    return this.refreshInFlight;
  }

  private async toError(response: Response): Promise<ApiError> {
    let body: Partial<ApiErrorBody["error"]> = {};
    try {
      const parsed = (await response.json()) as ApiErrorBody;
      body = parsed?.error ?? {};
    } catch {
      // A non-JSON failure (a proxy error page, say) still becomes an ApiError.
    }
    return new ApiError(response.status, body);
  }
}
