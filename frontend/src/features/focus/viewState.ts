import { useEffect, useState, type Dispatch, type SetStateAction } from "react";

type ViewState = Record<string, string | number | string[]>;
type StorageReader = Pick<Storage, "getItem">;

export function viewStateKey(profileId: string, area: string): string {
  return `fluxo.view.v1:${encodeURIComponent(profileId)}:${area}`;
}

export function readViewState<T extends ViewState>(storage: StorageReader, key: string, defaults: T): T {
  try {
    const saved: unknown = JSON.parse(storage.getItem(key) ?? "null");
    if (!saved || typeof saved !== "object" || Array.isArray(saved)) return defaults;
    const result = { ...defaults };
    for (const field of Object.keys(defaults) as (keyof T)[]) {
      const value = (saved as Record<string, unknown>)[String(field)];
      const initial = defaults[field];
      if (typeof initial === "string" && typeof value === "string") result[field] = value as T[keyof T];
      if (typeof initial === "number" && typeof value === "number" && Number.isFinite(value)) result[field] = value as T[keyof T];
      if (Array.isArray(initial) && Array.isArray(value) && value.every((item) => typeof item === "string")) result[field] = value as T[keyof T];
    }
    return result;
  } catch {
    return defaults;
  }
}

// Session storage keeps each account, area and browser tab independent. No server
// requests are needed to return from a card or reload the current workspace.
export function useViewState<T extends ViewState>(profileId: string, area: string, defaults: T): [T, Dispatch<SetStateAction<T>>] {
  const key = viewStateKey(profileId, area);
  const [state, setState] = useState(() => {
    try { return readViewState(window.sessionStorage, key, defaults); }
    catch { return defaults; }
  });
  useEffect(() => {
    try { window.sessionStorage.setItem(key, JSON.stringify(state)); }
    catch { /* Navigation remains usable when browser storage is unavailable. */ }
  }, [key, state]);
  return [state, setState];
}
