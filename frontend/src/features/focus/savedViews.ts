import type { FocusView } from "./focus";

export type SavedViewFilters = {
  query: string;
  companyId: string;
  status: string;
  priority: string;
  focusView: FocusView;
};

export type SavedView = SavedViewFilters & {
  id: string;
  name: string;
};

export function buildSavedView(
  id: string,
  name: string,
  filters: SavedViewFilters,
): SavedView {
  const cleanName = name.trim().replace(/\s+/g, " ");
  if (cleanName.length < 2) throw new Error("Dê um nome com pelo menos 2 caracteres.");
  if (cleanName.length > 40) throw new Error("Use um nome com até 40 caracteres.");
  return {
    id,
    name: cleanName,
    query: filters.query.trim().slice(0, 120),
    companyId: filters.companyId,
    status: filters.status,
    priority: filters.priority,
    focusView: filters.focusView,
  };
}

