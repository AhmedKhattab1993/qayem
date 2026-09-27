import { useEffect, useState } from "react";
import { api } from "./lib";
import type { Pinned } from "./store";
import type { CompoundDetail, Developer } from "./types";

export type Loaded =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; kind: "compound"; data: CompoundDetail }
  | { status: "ready"; kind: "developer"; data: Developer };

const id = (item: Pinned) => `${item.kind}:${item.key}`;

/** Load pinned compounds and developers; missing ones stay listed with their error. */
export function usePinned(items: Pinned[]) {
  const signature = items.map(id).join("|");
  const [entries, setEntries] = useState<Record<string, Loaded>>({});
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    for (const item of items) {
      const path = `/${item.kind === "compound" ? "compounds" : "developers"}/${encodeURIComponent(item.key)}`;
      setEntries((current) => (current[id(item)]?.status === "ready" ? current : { ...current, [id(item)]: { status: "loading" } }));
      api<CompoundDetail | Developer>(path, controller.signal)
        .then((data) =>
          setEntries((current) => ({
            ...current,
            [id(item)]: item.kind === "compound"
              ? { status: "ready", kind: "compound", data: data as CompoundDetail }
              : { status: "ready", kind: "developer", data: data as Developer },
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
