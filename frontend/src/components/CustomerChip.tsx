import clsx from "clsx";
import { MessageCircle, Phone } from "lucide-react";

import { Avatar } from "@/components/ui";
import { openWhatsApp } from "@/lib/whatsapp";

export interface ChipPerson {
  id?: string;
  full_name?: string;
  first_name?: string;
  last_name?: string;
  primary_phone?: string | null;
  mobile?: string | null;
  phones?: string[] | null;
}

function displayName(person: ChipPerson): string {
  return (
    person.full_name?.trim() ||
    `${person.first_name ?? ""} ${person.last_name ?? ""}`.trim() ||
    "Unnamed"
  );
}

function phoneOf(person: ChipPerson): string | null {
  return person.primary_phone || person.mobile || person.phones?.[0] || null;
}

/**
 * A person, their number, and a way to reach them — used everywhere a customer
 * appears so an agent never has to open a record just to find the phone number.
 *
 * The WhatsApp icon opens `wa.me` in a new tab: the agent's own WhatsApp, message
 * prefilled, nothing sent until they press send.
 */
export function CustomerChip({
  person,
  message,
  onClick,
  compact = false,
  className,
}: {
  person: ChipPerson;
  /** Prefilled WhatsApp text — see `waTemplates`. */
  message?: string;
  onClick?: () => void;
  compact?: boolean;
  className?: string;
}) {
  const name = displayName(person);
  const phone = phoneOf(person);

  return (
    <span className={clsx("flex min-w-0 items-center gap-2", className)}>
      {!compact && (
        <Avatar first={person.first_name ?? name} last={person.last_name ?? ""} size={26} />
      )}
      <span className="min-w-0">
        <button
          type="button"
          onClick={onClick}
          disabled={!onClick}
          className={clsx(
            "block max-w-full truncate text-left font-medium",
            onClick && "hover:text-primary-600 hover:underline"
          )}
          title={name}
        >
          {name}
        </button>
        {phone && (
          <span className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
            <a
              href={`tel:${phone}`}
              className="flex items-center gap-1 hover:text-primary-600"
              onClick={(e) => e.stopPropagation()}
              title={`Call ${phone}`}
            >
              <Phone size={11} />
              {phone}
            </a>
            <button
              type="button"
              title={`WhatsApp ${name}`}
              aria-label={`Open WhatsApp chat with ${name}`}
              className="text-emerald-600 transition-colors hover:text-emerald-500 dark:text-emerald-400"
              onClick={(e) => {
                e.stopPropagation();
                openWhatsApp(phone, message);
              }}
            >
              <MessageCircle size={13} />
            </button>
          </span>
        )}
      </span>
    </span>
  );
}

/** Just the WhatsApp icon, for tight spots like a table cell. */
export function WhatsAppButton({
  phone,
  message,
  label,
}: {
  phone: string | null | undefined;
  message?: string;
  label?: string;
}) {
  if (!phone) return null;
  return (
    <button
      type="button"
      title={label ?? `WhatsApp ${phone}`}
      aria-label={label ?? `Open WhatsApp chat with ${phone}`}
      className="text-emerald-600 transition-colors hover:text-emerald-500 dark:text-emerald-400"
      onClick={(e) => {
        e.stopPropagation();
        openWhatsApp(phone, message);
      }}
    >
      <MessageCircle size={15} />
    </button>
  );
}
