export type LanguageBasicsPreference = "unknown" | "has_basics" | "no_basics";

function languageBasicsStorageKey(learnerId: string): string {
  return `code-navi:language-basics:${learnerId}`;
}

export function readLanguageBasics(learnerId: string): LanguageBasicsPreference {
  if (typeof window === "undefined") return "unknown";
  const value = window.localStorage.getItem(languageBasicsStorageKey(learnerId));
  return value === "has_basics" || value === "no_basics" ? value : "unknown";
}

export function saveLanguageBasics(
  learnerId: string,
  preference: LanguageBasicsPreference,
): void {
  if (typeof window === "undefined" || preference === "unknown") return;
  window.localStorage.setItem(languageBasicsStorageKey(learnerId), preference);
  window.dispatchEvent(new Event("code-navi:language-basics-change"));
}
