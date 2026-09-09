export function formatMoney(value: number | null | undefined, currency = "INR"): string {
  const amount = Number(value ?? 0);
  try {
    return new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(amount);
  } catch {
    return `${currency} ${amount.toLocaleString()}`;
  }
}

/**
 * Parse a timestamp from the API.
 *
 * The server stores and serialises naive UTC — "2026-09-09T15:28:24.400156", with
 * no zone on the end. JavaScript reads an ISO string that has a time but no zone as
 * **local** time, so in IST every timestamp in the app was five and a half hours
 * out: a note written seconds ago read "5h ago", and an activity timeline claimed
 * this morning's work happened before dawn.
 *
 * Date-only values ("2026-09-09") are already parsed as UTC and are left alone.
 */
function parse(value: string): Date {
  const naiveDateTime = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(value) && !/(Z|[+-]\d{2}:?\d{2})$/.test(value);
  return new Date(naiveDateTime ? `${value.replace(" ", "T")}Z` : value);
}

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const d = parse(value);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const d = parse(value);
  return d.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function timeAgo(value: string): string {
  const seconds = Math.floor((Date.now() - parse(value).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(value);
}

export function initials(first?: string | null, last?: string | null): string {
  return `${(first || "").charAt(0)}${(last || "").charAt(0)}`.toUpperCase() || "?";
}

export function fullName(u?: { first_name: string; last_name: string } | null): string {
  if (!u) return "—";
  return `${u.first_name} ${u.last_name}`.trim();
}
