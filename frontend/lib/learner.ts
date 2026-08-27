/**
 * Unified anonymous learner profile key.
 *
 * The learning portrait (学情画像) aggregates by this id, which must be the
 * SAME value the practice module already mints — it reads the same storage key
 * (``code-navi-compiler-learner-id``) so quiz attempts and confusion marks from
 * the learning module land on the same portrait as the practice records.
 * Only the opaque UUID is stored — never a credential, name or email.
 */

const LEARNER_ID_STORAGE_KEY = "code-navi-compiler-learner-id";

/** Fallback zero UUID used in server-rendered / non-secure contexts. */
const SSR_FALLBACK = "00000000-0000-4000-8000-000000000000";

/**
 * Mint a UUID v4 that satisfies the backend's profile-key pattern.
 *
 * ``crypto.randomUUID`` is only defined in secure contexts (HTTPS or
 * localhost). On plain HTTP through a LAN hostname or address it is undefined
 * and throws at runtime, so fall back to a v4-shaped UUID built from
 * ``crypto.getRandomValues`` (available everywhere), then ``Math.random`` as a
 * last resort.
 */
export function newUuidV4(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
    bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10xx
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  // Last resort: pseudo-random but still v4-shaped.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Return this browser's unified profile key, minting a UUID v4 on first use.
 *
 * Shared by the practice and learning modules so both write to the same
 * portrait. Returns the SSR fallback on the server side (never persisted).
 */
export function getOrCreateLearnerId(): string {
  if (typeof window === "undefined") return SSR_FALLBACK;
  const existing = window.localStorage.getItem(LEARNER_ID_STORAGE_KEY);
  if (existing) return existing;
  const minted = newUuidV4();
  window.localStorage.setItem(LEARNER_ID_STORAGE_KEY, minted);
  return minted;
}
