import { useEffect, useState } from "react";

/**
 * useState that survives navigation and reloads, backed by localStorage.
 *
 * Used for list filters, sort and page size, so going into a record and
 * coming back lands on the same view instead of resetting to the defaults -
 * "back and forth retains the filters until they're changed".
 *
 * Deliberately per-viewer and best-effort: localStorage can throw (private
 * windows, blocked site data) and can hold a value written by an older
 * build, so every read and write is guarded and a bad value falls back to
 * `initial` rather than breaking the page. Same discipline the Employees
 * column picker already used for its own saved column set.
 *
 * Bump the `key` (…_v2) whenever a stored shape changes meaning, so nobody
 * is left with a saved value that silently means something else.
 */
export default function usePersistedState(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw === null) return initial;
      const parsed = JSON.parse(raw);
      // A stored value of a different type than the default is a leftover
      // from an older build - ignore it instead of feeding a filter
      // something it can't use.
      if (parsed === null || typeof parsed !== typeof initial) return initial;
      return parsed;
    } catch {
      return initial;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Storage unavailable or full - the filter still works for this
      // session, it just won't be remembered.
    }
  }, [key, value]);

  return [value, setValue];
}
