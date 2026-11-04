import { ApiError, apiUrl, request } from "@/lib/api";
import type {
  AccountStatus,
  AdminResetCode,
  ConsentState,
  DeviceSession,
  ErasureReceipt,
  HistoryPage,
  MatterCount,
  PrivacyConfiguration,
  RetentionStatus,
  StepUp,
} from "@/lib/types-platform";
import type { User } from "@/lib/types";

// ------------------------------------------------------------------- public

export const getPrivacyConfiguration = () =>
  request<PrivacyConfiguration>("/account/privacy", {}, false);

export const redeemResetCode = (email: string, code: string, newPassword: string) =>
  request<void>(
    "/account/password-reset/redeem",
    { method: "POST", body: JSON.stringify({ email, code, new_password: newPassword }) },
    false,
  );

export const requestResetByMail = (email: string) =>
  request<{ status: string }>(
    "/account/password-reset/request",
    { method: "POST", body: JSON.stringify({ email }) },
    false,
  );

// ---------------------------------------------------------------- your account

export const getAccountStatus = () => request<AccountStatus>("/account/status");

export const updateProfile = (changes: { name?: string; email?: string; current_password?: string }) =>
  request<User>("/account/profile", { method: "PATCH", body: JSON.stringify(changes) });

export const changePassword = (currentPassword: string, newPassword: string) =>
  request<{ status: string }>("/account/password", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });

export const acceptConsent = (noticeVersion: string) =>
  request<ConsentState>("/account/consent", {
    method: "POST",
    body: JSON.stringify({ notice_version: noticeVersion }),
  });

export const withdrawConsent = () =>
  request<ConsentState>("/account/consent/withdraw", { method: "POST" });

export const listDeviceSessions = () =>
  request<{ items: DeviceSession[] }>("/account/sessions").then(body => body.items);

export const revokeDeviceSession = (id: string) =>
  request<void>(`/account/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });

export const revokeOtherSessions = () =>
  request<{ revoked: number }>("/account/sessions/revoke-others", { method: "POST" });

export const beginMfaEnrollment = (password: string) =>
  request<{ secret: string; otpauth_uri: string }>("/account/mfa/enroll", {
    method: "POST",
    body: JSON.stringify({ password }),
  });

export const confirmMfaEnrollment = (code: string) =>
  request<{ codes: string[] }>("/account/mfa/confirm", {
    method: "POST",
    body: JSON.stringify({ code }),
  });

export const disableMfa = (stepUp: StepUp) =>
  request<void>("/account/mfa/disable", { method: "POST", body: JSON.stringify(stepUp) });

export const replaceRecoveryCodes = (stepUp: StepUp) =>
  request<{ codes: string[] }>("/account/mfa/recovery-codes", {
    method: "POST",
    body: JSON.stringify(stepUp),
  });

/** The whole record comes back as a file. Never a link, which could be replayed. */
export async function downloadMyData(stepUp: StepUp): Promise<Blob> {
  const response = await fetch(`${apiUrl()}/account/export`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(stepUp),
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      // keep the status text
    }
    throw new ApiError(String(detail), response.status);
  }
  return response.blob();
}

export const eraseMyAccount = (stepUp: StepUp, confirm: string) =>
  request<ErasureReceipt>("/account/erase", {
    method: "POST",
    body: JSON.stringify({ ...stepUp, confirm }),
  });

// --------------------------------------------------------------------- history

export function listHistorySessions(options: {
  limit?: number;
  cursor?: string | null;
  pinned?: boolean;
  matter?: string | null;
} = {}): Promise<HistoryPage> {
  const params = new URLSearchParams({ limit: String(options.limit ?? 30) });
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.pinned !== undefined) params.set("pinned", String(options.pinned));
  if (options.matter) params.set("matter", options.matter);
  return request<HistoryPage>(`/history/sessions?${params}`);
}

/** In the body, not the URL: what someone searches for is as private as what they ask. */
export const searchHistory = (term: string, cursor?: string | null, limit = 30) =>
  request<HistoryPage>("/history/search", {
    method: "POST",
    body: JSON.stringify({ term, limit, cursor: cursor ?? null }),
  });

export const setSessionPinned = (id: string, pinned: boolean) =>
  request<void>(`/history/sessions/${encodeURIComponent(id)}/pin`, {
    method: "PUT",
    body: JSON.stringify({ pinned }),
  });

export const setSessionMatter = (id: string, matter: string | null) =>
  request<void>(`/history/sessions/${encodeURIComponent(id)}/matter`, {
    method: "PUT",
    body: JSON.stringify({ matter }),
  });

export const listMatters = () =>
  request<{ items: MatterCount[] }>("/history/matters").then(body => body.items);

// --------------------------------------------------------------- administrators

export const adminIssueResetCode = (email: string, resetMfa: boolean) =>
  request<AdminResetCode>("/account/admin/reset-code", {
    method: "POST",
    body: JSON.stringify({ email, reset_mfa: resetMfa }),
  });

export const adminEraseAccount = (email: string, adminPassword: string, confirm: string, mfaCode?: string) =>
  request<ErasureReceipt>("/account/admin/erase", {
    method: "POST",
    body: JSON.stringify({ email, admin_password: adminPassword, confirm, mfa_code: mfaCode || null }),
  });

export const adminRetentionStatus = () => request<RetentionStatus>("/account/admin/retention");

export const adminRunRetention = () =>
  request<{ erased_conversations: number }>("/account/admin/retention/run", { method: "POST" });
