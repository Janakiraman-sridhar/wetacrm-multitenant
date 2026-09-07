import { tokenStore } from "@/lib/api";

/**
 * Support impersonation: a platform admin opening a tenant workspace as one of its users.
 *
 * The platform admin's own tokens are parked here so the session can be handed back
 * intact on exit — otherwise leaving would mean signing in again. The impersonation
 * token itself is short-lived (60 minutes, enforced by the backend) and every use is
 * audited against the real admin, not the user being acted as.
 *
 * Everything here depends on `localStorage`, and a browser that blocks it would
 * otherwise fail *silently*: the token would not be stored, the reload would find no
 * session, and the admin would land back on the sign-in screen with no explanation.
 * So storage is probed up front and failures are raised, not swallowed.
 */

const KEY = "weta_impersonation";

export interface ImpersonationState {
  tenantId: string;
  tenantName: string;
  actingAsEmail: string;
  /** The platform admin's own tokens, restored on exit. */
  adminAccess: string;
  adminRefresh: string;
  startedAt: number;
}

export class StorageUnavailable extends Error {
  constructor() {
    super(
      "Your browser is blocking site storage, so the workspace session cannot be held. " +
        "Private browsing or a cookie/storage block is the usual cause."
    );
    this.name = "StorageUnavailable";
  }
}

/** Can we actually persist a session? Checked before anything is torn down. */
export function storageWorks(): boolean {
  try {
    const probe = "__weta_probe__";
    localStorage.setItem(probe, "1");
    localStorage.removeItem(probe);
    return true;
  } catch {
    return false;
  }
}

export function readImpersonation(): ImpersonationState | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as ImpersonationState) : null;
  } catch {
    return null;
  }
}

export function isImpersonating(): boolean {
  return readImpersonation() !== null;
}

/**
 * Swap the platform session for a tenant one, remembering how to get back.
 *
 * Throws rather than returning false, so a caller cannot navigate away believing it
 * worked. The admin's own tokens are captured *before* anything is overwritten.
 */
export function startImpersonation(
  token: string,
  tenantId: string,
  tenantName: string,
  actingAsEmail: string
): void {
  if (!token) throw new Error("The server did not return a session for this workspace.");
  if (!storageWorks()) throw new StorageUnavailable();

  const state: ImpersonationState = {
    tenantId,
    tenantName,
    actingAsEmail,
    adminAccess: tokenStore.access ?? "",
    adminRefresh: tokenStore.refresh ?? "",
    startedAt: Date.now(),
  };

  localStorage.setItem(KEY, JSON.stringify(state));
  // No refresh token: an impersonation session is meant to expire, not renew.
  tokenStore.set(token, "");

  if (tokenStore.access !== token) {
    // Storage accepted the probe but not the token — restore and fail loudly rather
    // than reloading into a signed-out state.
    localStorage.removeItem(KEY);
    throw new StorageUnavailable();
  }
}

/** Hand the platform admin their own session back. */
export function stopImpersonation(): void {
  const state = readImpersonation();
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore — the tokens below matter more */
  }
  if (state?.adminAccess) {
    tokenStore.set(state.adminAccess, state.adminRefresh);
  } else {
    tokenStore.clear();
  }
}

/** Minutes left before the backend stops honouring this session. */
export function minutesRemaining(limitMinutes = 60): number | null {
  const state = readImpersonation();
  if (!state?.startedAt) return null;
  const elapsed = (Date.now() - state.startedAt) / 60_000;
  return Math.max(0, Math.round(limitMinutes - elapsed));
}
