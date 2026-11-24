import { NavLink } from "react-router-dom";
import { Building2, Landmark, MapPin } from "lucide-react";
import { t } from "../locale";

const TABS = [
  { to: "/districts", label: "Districts", icon: MapPin },
  { to: "/compounds", label: "Compounds", icon: Building2 },
  { to: "/developers", label: "Developers", icon: Landmark },
] as const;

/** The price guide is one section with three doors: a district, a compound or a developer. */
export function GuideTabs() {
  return (
    <nav className="guide-tabs" aria-label={t("Price guide")}>
      {TABS.map(({ to, label, icon: Icon }) => (
        <NavLink key={to} to={to} end className={({ isActive }) => (isActive ? "is-active" : "")}>
          <Icon size={15} /> {t(label)}
        </NavLink>
      ))}
    </nav>
  );
}
