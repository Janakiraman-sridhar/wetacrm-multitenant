import { tokenStore } from "@/lib/api";

/**
 * Support impersonation: a platform admin opening a tenant workspace as one of its users.
 *
 * The platform admin's own tokens are parked here so the session can be handed back
 * intact when they exit — otherwise leaving an impersonation would mean signing in
 * again. The impersonation token itself is short-lived (60 minutes, enforced by the
 * backend) and every use is audited against the real admin, not the user being acted as.
 */

const KEY = "weta_impersonation";

export interface ImpersonationState {
  tenantId: string;
  tenantName: string;
  actingAsEmail: string;
  /** The platform admin's own tokens, restored on exit. */
  adminAccess: string;
  adminRefresh: string;
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

/** Swap the platform session for a tenant one, remembering how to get back. */
export function startImpersonation(
  token: string,
  tenantId: string,
  tenantName: string,
  actingAsEmail: string
): void {
  const state: ImpersonationState = {
    tenantId,
    tenantName,
    actingAsEmail,
    adminAccess: tokenStore.access ?? "",
    adminRefresh: tokenStore.refresh ?? "",
  };
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* storage unavailable — the banner will be missing but the session still works */
  }
  // No refresh token for an impersonation session: it is meant to expire.
  tokenStore.set(token, "");
}

/** Hand the platform admin their own session back. */
export function stopImpersonation(): void {
  const state = readImpersonation();
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
  if (state?.adminAccess) {
    tokenStore.set(state.adminAccess, state.adminRefresh);
  } else {
    tokenStore.clear();
  }
}
