import { useEffect, useState } from "react";
import { api, nameOf } from "./lib";
import type { Pinned } from "./store";
import type { CompoundDetail, Developer, UnitDetail } from "./types";
import { unitName } from "./components/UnitTable";

export type Loaded =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; kind: "compound"; data: CompoundDetail }
  | { status: "ready"; kind: "developer"; data: Developer }
  | { status: "ready"; kind: "unit"; data: UnitDetail };
const folder = { compound: "compounds", developer: "developers", unit: "units" } as const;
/** Where a pinned compound, developer or unit lives on the site. */
export const pinnedPath = (item: Pinned) => `/${folder[item.kind]}/${encodeURIComponent(item.key)}`;

const id = (item: Pinned) => `${item.kind}:${item.key}`;

/** Load pinned compounds and developers; missing ones stay listed with their error. */
export function usePinned(items: Pinned[]) {
  const signature = items.map(id).join("|");
  const [entries, setEntries] = useState<Record<string, Loaded>>({});
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    for (const item of items) {
      const path = pinnedPath(item);
      setEntries((current) => (current[id(item)]?.status === "ready" ? current : { ...current, [id(item)]: { status: "loading" } }));
      api<CompoundDetail | Developer | UnitDetail>(path, controller.signal)
        .then((data) =>
          setEntries((current) => ({
            ...current,
            [id(item)]:
              item.kind === "compound"
                ? { status: "ready", kind: "compound", data: data as CompoundDetail }
                : item.kind === "developer"
                  ? { status: "ready", kind: "developer", data: data as Developer }
                  : { status: "ready", kind: "unit", data: data as UnitDetail },
          })),
        )
        .catch((error) => {
          if (error.name !== "AbortError")
            setEntries((current) => ({ ...current, [id(item)]: { status: "error", error: error.message } }));
        });
    }
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, revision]);
  return { get: (item: Pinned): Loaded => entries[id(item)] ?? { status: "loading" }, retry: () => setRevision((n) => n + 1) };
}

/** A pinned entry's name in the interface language once loaded; the stored (English) name until then. */
export const pinnedName = (item: Pinned, entry: Loaded) =>
  entry.status !== "ready"
    ? item.name
    : entry.kind === "unit"
      ? unitName(entry.data.unit)
      : nameOf(entry.kind === "compound" ? entry.data.compound : entry.data)!;
