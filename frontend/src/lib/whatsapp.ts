/**
 * Click-to-chat links.
 *
 * `wa.me` opens the agent's own WhatsApp — Web on desktop, the app on mobile — with
 * the message prefilled. No integration, no approvals, no per-message cost; the
 * agent presses send. The Cloud API arrives in a later phase for automated and bulk
 * sends, behind the same helpers.
 */

/** Strip a number to the digits `wa.me` expects (country code, no `+`). */
export function toWaNumber(phone: string | null | undefined): string | null {
  if (!phone) return null;
  const digits = phone.replace(/\D/g, "");
  if (digits.length < 10) return null;
  // A bare 10-digit Indian number needs its country code; anything longer has one.
  return digits.length === 10 ? `91${digits}` : digits;
}

export function waLink(phone: string | null | undefined, message?: string): string | null {
  const number = toWaNumber(phone);
  if (!number) return null;
  const text = message ? `?text=${encodeURIComponent(message)}` : "";
  return `https://wa.me/${number}${text}`;
}

/** Message templates for the places an agent starts a conversation from. */
export const waTemplates = {
  birthday: (name: string, agent: string) =>
    `Dear ${name}, wishing you a very happy birthday and a wonderful year ahead. — ${agent}`,
  renewal: (name: string, detail: string) =>
    `Dear ${name}, your policy ${detail} is coming up for renewal. Shall I get the renewal quote ready?`,
  followUp: (name: string) =>
    `Dear ${name}, following up on our conversation. Let me know a good time to talk.`,
  documents: (name: string) =>
    `Dear ${name}, could you please share the pending documents when you get a moment? Thank you.`,
};

export function openWhatsApp(phone: string | null | undefined, message?: string): boolean {
  const url = waLink(phone, message);
  if (!url) return false;
  window.open(url, "_blank", "noopener,noreferrer");
  return true;
}
