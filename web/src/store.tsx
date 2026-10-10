import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

export type EntityKind = "compound" | "developer" | "unit";
export interface Pinned {
  kind: EntityKind;
  key: string;
  name: string;
}
/** A Units search kept in this browser, with the newest listing seen when it was last opened. */
export interface SavedSearch {
  query: string;
  seen: number;
}
interface Store {
  searches: SavedSearch[];
  toggleSearch: (query: string, newest: number) => void;
  markSeen: (query: string, newest: number) => void;
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
          v && ["compound", "developer", "unit"].includes(v.kind) && typeof v.key === "string" && typeof v.name === "string",
      )
      .slice(0, limit);
  } catch {
    return [];
  }
}
function readSearches(): SavedSearch[] {
  try {
    const values: unknown = JSON.parse(localStorage.getItem("qayem:searches") || "[]");
    if (!Array.isArray(values)) return [];
    return values
      .filter((v): v is SavedSearch => v && typeof v.query === "string" && typeof v.seen === "number")
      .slice(0, 20);
  } catch {
    return [];
  }
}
function persist(key: string, items: unknown[]) {
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
  const [searches, setSearches] = useState(readSearches);
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
      return setMessage("Compare compounds with compounds, developers with developers, and units with units.");
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
  const toggleSearch = (query: string, newest: number) => {
    const removing = searches.some((item) => item.query === query);
    if (!removing && searches.length >= 20) return setMessage("You can save up to 20 searches.");
    const next = removing ? searches.filter((item) => item.query !== query) : [...searches, { query, seen: newest }];
    setSearches(next);
    setMessage(persist("qayem:searches", next) ? (removing ? "Search removed" : "Search saved to your watchlist") : storageNotice);
  };
  const markSeen = useCallback((query: string, newest: number) => {
    setSearches((current) => {
      if (!current.some((item) => item.query === query && item.seen < newest)) return current;
      const next = current.map((item) => (item.query === query ? { ...item, seen: newest } : item));
      persist("qayem:searches", next);
      return next;
    });
  }, []);
  const clearCompare = () => {
    setCompare([]);
    if (!persist("qayem:compare-entities", [])) setMessage(storageNotice);
  };
  return (
    <Context.Provider
      value={{ searches, toggleSearch, markSeen, watch, compare, toggleWatch, toggleCompare, clearCompare, toast, message }}
    >
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
