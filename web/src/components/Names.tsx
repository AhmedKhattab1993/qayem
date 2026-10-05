import { Fragment, type ReactNode } from "react";
import { sep } from "../lib";

/** Source names joined with the list separator. Each name keeps its own direction, so an Arabic name
 * in the English interface (or a Latin one in Arabic) cannot reorder the rest of the line. */
export function NameList({ items }: { items: ReactNode[] }) {
  return (
    <>
      {items
        .filter((item) => item != null && item !== false && item !== "")
        .map((item, index) => (
          <Fragment key={index}>
            {index > 0 && sep()}
            <bdi>{item}</bdi>
          </Fragment>
        ))}
    </>
  );
}
