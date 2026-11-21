import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { number, place, useCatalog } from "../lib";
import { t } from "../locale";
import { Loading } from "../components/States";

export default function Districts() {
  const catalog = useCatalog();
  const districts = (catalog?.districts ?? []).filter((d) => d.units >= 5);
  return (
    <div className="page-enter">
      <header className="page-head">
        <div className="page">
          <span className="eyebrow">{t("Districts")}</span>
          <h1 className="display">
            {t("Where to buy,")} <em>{t("district by district.")}</em>
          </h1>
          <p className="lede">
            {t("Resale prices per m², the developer’s prices today and the opportunities in each district, from every listing compared.")}
          </p>
        </div>
      </header>
      <div className="page">
        {!catalog ? (
          <Loading />
        ) : (
          <ul className="district-grid">
            {districts.map((district) => (
              <li key={district.key}>
                <Link to={`/districts/${encodeURIComponent(district.key)}`}>
                  <b>{place(district.name)}</b>
                  <small className="num">{t("{n} listings", { n: number(district.units), count: district.units })}</small>
                  <ArrowUpRight size={16} className="flip-rtl" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
