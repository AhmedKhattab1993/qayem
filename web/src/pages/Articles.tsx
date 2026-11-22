import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, ArrowUpRight, Languages, Newspaper } from "lucide-react";
import { date, nameOf, number, periodLabel, safeExternalUrl, useApi, useTitle } from "../lib";
import { getLanguage, t } from "../locale";
import { EmptyState, ErrorState, Loading } from "../components/States";
import type { Article, ArticleBlock, ArticlePage as ArticleList, ArticleSummary } from "../types";

const KINDS: Record<string, string> = {
  index: "Monthly index",
  move: "Price move",
  developer_prices: "Developer prices",
  rates: "Interest rates",
  developer_report: "Developer results",
  guide: "Guide",
  explainer: "Explainer",
};
const kindLabel = (kind: string) => t(KINDS[kind] ?? "Article");

function Related({ article }: { article: Pick<ArticleSummary, "district" | "compound"> }) {
  if (!article.district && !article.compound) return null;
  return (
    <span className="article-related">
      {article.compound && <Link to={`/compounds/${encodeURIComponent(article.compound.key)}`}>{nameOf(article.compound)}</Link>}
      {article.district && <Link to={`/districts/${encodeURIComponent(article.district.key)}`}>{nameOf(article.district)}</Link>}
    </span>
  );
}

export function Articles() {
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get("page")) || 1);
  const lang = getLanguage();
  const { data, error, missing, retry } = useApi<ArticleList>(`/articles?lang=${lang}&page=${page}`);
  return (
    <div className="page-enter">
      <header className="page-head">
        <div className="page">
          <span className="eyebrow">{t("Articles")}</span>
          <h1 className="display">{t("What the figures say")}</h1>
          <p className="lede">
            {t("Short reports on Egypt’s property prices, each built on Qayem’s own figures and tied to a district or compound guide.")}
          </p>
        </div>
      </header>
      <div className="page section-tight">
        {error && !missing ? (
          <ErrorState message={error} retry={retry} />
        ) : missing || (data && data.items.length === 0) ? (
          <EmptyState
            icon={<Newspaper size={26} />}
            title={t("No articles yet")}
            text={t("The first reports come with the monthly index. Until then, the map and the guides have every figure.")}
            action={
              <Link className="btn btn-ink" to="/map">
                {t("Open the map")} <ArrowRight size={16} className="flip-rtl" />
              </Link>
            }
          />
        ) : !data ? (
          <Loading />
        ) : (
          <>
            <ol className="article-list">
              {data.items.map((item) => (
                <li key={item.slug}>
                  <article>
                    <p className="article-meta">
                      <span className="tag">{kindLabel(item.kind)}</span>
                      <time dateTime={item.published_at}>{date(item.published_at)}</time>
                    </p>
                    <h2>
                      <Link to={`/articles/${encodeURIComponent(item.slug)}`} dir="auto">
                        {item.title}
                      </Link>
                    </h2>
                    <p dir="auto">{item.summary}</p>
                    <Related article={item} />
                  </article>
                </li>
              ))}
            </ol>
            {data.pages > 1 && (
              <nav className="pager" aria-label={t("Pages")}>
                <button type="button" className="btn btn-sm" disabled={page <= 1} onClick={() => setParams({ page: String(page - 1) })}>
                  <ArrowLeft size={15} className="flip-rtl" /> {t("Newer")}
                </button>
                <span className="num">{t("Page {page} of {pages}", { page: number(page), pages: number(data.pages) })}</span>
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={page >= data.pages}
                  onClick={() => setParams({ page: String(page + 1) })}
                >
                  {t("Older")} <ArrowRight size={15} className="flip-rtl" />
                </button>
              </nav>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/** Blocks are rendered as text only: nothing from the API is read as HTML. */
function Block({ block }: { block: ArticleBlock }) {
  switch (block.type) {
    case "h2":
      return <h2>{block.text}</h2>;
    case "p":
      return <p>{block.text}</p>;
    case "list":
      return (
        <ul>
          {block.items.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      );
    case "figure":
      return (
        <figure className="article-figure">
          <strong className="num">{typeof block.value === "number" ? number(block.value) : block.value}</strong>
          <figcaption>
            {block.label}
            {block.note && <small>{block.note}</small>}
          </figcaption>
        </figure>
      );
    case "table":
      return (
        <div className="ledger article-table">
          <table>
            <thead>
              <tr>
                {block.columns.map((column, index) => (
                  <th key={index} scope="col">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, index) => (
                <tr key={index}>
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex} className={typeof cell === "number" ? "num" : undefined}>
                      {typeof cell === "number" ? number(cell) : cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    default:
      return null;
  }
}

export function ArticlePage() {
  const { slug = "" } = useParams();
  const { data, error, missing, retry } = useApi<Article>(`/articles/${encodeURIComponent(slug)}`);
  useTitle(data?.title);
  if (error)
    return (
      <div className="page">
        <ErrorState message={error} retry={retry} missing={missing} />
      </div>
    );
  if (!data) return <Loading />;
  const sources = data.sources ?? [];
  return (
    <article className="article page-enter" lang={data.lang} dir={data.lang === "ar" ? "rtl" : "ltr"}>
      <header className="page-head">
        <div className="page article-column">
          <Link className="link-arrow back" to="/articles">
            <ArrowLeft size={15} className="flip-rtl" /> {t("All articles")}
          </Link>
          <p className="article-meta">
            <span className="tag">{kindLabel(data.kind)}</span>
            <time dateTime={data.published_at}>{date(data.published_at)}</time>
            {data.updated_at && data.updated_at !== data.published_at && (
              <span>{t("Updated {date}", { date: date(data.updated_at) })}</span>
            )}
          </p>
          <h1 className="display">{data.title}</h1>
          <p className="lede">{data.summary}</p>
          <p className="article-byline">
            {t("By {byline}", { byline: t(data.byline || "Qayem data desk") })}
            {data.period && <span className="num"> · {t("Listings seen {period}", { period: periodLabel(data.period) })}</span>}
          </p>
          <div className="entity-bar">
            {data.translation && (
              <Link className="btn btn-sm" to={`/articles/${encodeURIComponent(data.translation)}`} lang={data.lang === "ar" ? "en" : "ar"} dir={data.lang === "ar" ? "ltr" : "rtl"}>
                <Languages size={15} /> {data.lang === "ar" ? "Read in English" : "اقرأ بالعربية"}
              </Link>
            )}
            <Related article={data} />
          </div>
        </div>
      </header>
      <div className="page article-column prose article-body">
        {data.blocks.map((block, index) => (
          <Block key={index} block={block} />
        ))}
        {sources.length > 0 && (
          <section className="article-sources">
            <h2>{t("Sources")}</h2>
            <ul>
              {sources.map((source) => {
                const url = safeExternalUrl(source.url);
                return (
                  <li key={source.name}>
                    {url ? (
                      <a href={url} target="_blank" rel="noreferrer">
                        <bdi>{source.name}</bdi>
                      </a>
                    ) : (
                      <bdi>{source.name}</bdi>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        )}
        <p className="notice notice-soft article-note">
          <span>
            {t("Written with AI from Qayem’s own figures by the Qayem data desk, and checked automatically: every number and date is matched against the data before it is published. Figures are asking prices, not sale prices or advice.")}{" "}
            <Link to="/methodology">{t("Read the methodology")}</Link>
            {" · "}
            <Link to={`/corrections?url=${encodeURIComponent(`/articles/${data.slug}`)}`}>{t("Report a mistake")}</Link>
          </span>
        </p>
        {(data.district || data.compound) && (
          <p>
            <Link
              className="link-arrow"
              to={data.compound ? `/compounds/${encodeURIComponent(data.compound.key)}` : `/districts/${encodeURIComponent(data.district!.key)}`}
            >
              {t("Open the price guide for {name}", { name: nameOf(data.compound ?? data.district) })}{" "}
              <ArrowUpRight size={15} className="flip-rtl" />
            </Link>
          </p>
        )}
      </div>
    </article>
  );
}
