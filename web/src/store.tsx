import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

export type EntityKind = "compound" | "developer";
export interface Pinned {
  kind: EntityKind;
  key: string;
  name: string;
}
interface Store {
  watch: Pinned[];
  compare: Pinned[];
  toggleWatch: (item: Pinned) => void;
  toggleCompare: (item: Pinned) => void;
  clearCompare: () => void;
  toast: (message: string) => void;
  message: string;
}
const Context = createContext<Store | null>(null);
const storageNotice = "Your selection will last for this visit only. Browser storage is unavailable.";
const same = (a: Pinned, b: Pinned) => a.kind === b.kind && a.key === b.key;

function read(key: string, limit: number): Pinned[] {
  try {
    const values: unknown = JSON.parse(localStorage.getItem(key) || "[]");
    if (!Array.isArray(values)) return [];
    return values
      .filter(
        (v): v is Pinned =>
          v && (v.kind === "compound" || v.kind === "developer") && typeof v.key === "string" && typeof v.name === "string",
      )
      .slice(0, limit);
  } catch {
    return [];
  }
}
function persist(key: string, items: Pinned[]) {
  try {
    localStorage.setItem(key, JSON.stringify(items));
    return true;
  } catch {
    return false;
  }
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [watch, setWatch] = useState(() => read("qayem:watch", 100));
  const [compare, setCompare] = useState(() => read("qayem:compare-entities", 3));
  const [message, setMessage] = useState("");
  const toast = useCallback((text: string) => setMessage(text), []);
  const toggleWatch = (item: Pinned) => {
    const removing = watch.some((w) => same(w, item));
    if (!removing && watch.length >= 100) return setMessage("Your watchlist holds up to 100 entries.");
    const next = removing ? watch.filter((w) => !same(w, item)) : [...watch, item];
    setWatch(next);
    setMessage(
      persist("qayem:watch", next) ? (removing ? "Removed from your watchlist" : "Added to your watchlist") : storageNotice,
    );
  };
  const toggleCompare = (item: Pinned) => {
    const removing = compare.some((c) => same(c, item));
    if (!removing && compare.length >= 3) return setMessage("You can compare up to 3. Remove one to add another.");
    if (!removing && compare.length && compare[0].kind !== item.kind)
      return setMessage("Compare compounds with compounds, and developers with developers.");
    const next = removing ? compare.filter((c) => !same(c, item)) : [...compare, item];
    setCompare(next);
    setMessage(
      persist("qayem:compare-entities", next)
        ? removing
          ? "Removed from comparison"
          : "Added to comparison"
        : storageNotice,
    );
  };
  const clearCompare = () => {
    setCompare([]);
    if (!persist("qayem:compare-entities", [])) setMessage(storageNotice);
  };
  return (
    <Context.Provider value={{ watch, compare, toggleWatch, toggleCompare, clearCompare, toast, message }}>
      {children}
    </Context.Provider>
  );
}
export function useStore() {
  const value = useContext(Context);
  if (!value) throw new Error("StoreProvider is required");
  return value;
}
export const isPinned = (list: Pinned[], kind: EntityKind, key: string) =>
  list.some((item) => item.kind === kind && item.key === key);
