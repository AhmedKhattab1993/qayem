import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, FileWarning } from "lucide-react";
import { t } from "../locale";
import { useGrowthConfig } from "../growth";
import { CaptureForm, lead } from "../components/Capture";

const TERMS: [string, string][] = [
  [
    "What Qayem is",
    "Qayem compares asking prices. It reads public property listings and developers’ published price lists in Egypt, and publishes medians, ranges and comparisons for districts, compounds and units, with the rules behind them on the methodology page.",
  ],
  [
    "Comparisons, not valuations or advice",
    "Nothing on Qayem is a valuation, an appraisal, an offer or investment, legal or financial advice. Egypt publishes no property sale prices: Qayem’s figures are asking prices and list prices, which can differ from what is finally paid. Check every unit, its papers and its price with the seller and the developer before you pay anything.",
  ],
  [
    "Aggregates only",
    "Qayem publishes figures about groups of listings: a median, a range, a count. Each figure says how many listings it rests on, which sites they come from, the period, and how confident it is. Where too few listings exist, no figure is published.",
  ],
  [
    "No listings or photos republished",
    "Qayem does not republish anyone’s listings, descriptions or photos, and keeps no seller’s or broker’s name or phone number. A unit page shows the facts Qayem compares (price, area, type, payment plan, place and date) and links to the listing on its own site.",
  ],
  [
    "Reusing Qayem’s figures",
    "The monthly Qayem Index is free to reuse under the Creative Commons Attribution 4.0 licence, with credit to “Qayem Index (qayem.ai)” and its month. Please do not copy the rest of the site in bulk.",
  ],
  [
    "Mistakes, corrections and takedowns",
    "If a figure is wrong, or a page shows something about you or your listing that should not be there, tell us on the corrections page. We reply by e-mail, correct what is wrong, and remove what should not be published, usually within two working days.",
  ],
  [
    "Changes",
    "These terms can change as Qayem grows; the date below says when they last did. Using the site after a change means accepting the new terms.",
  ],
];

export function Terms() {
  return (
    <div className="page-enter">
      <header className="page-head">
        <div className="page">
          <span className="eyebrow">{t("Terms of use")}</span>
          <h1 className="display">{t("How to read and use Qayem")}</h1>
          <p className="lede">{t("Short and plain: what Qayem’s figures are, what they are not, and how to reach us.")}</p>
        </div>
      </header>
      <div className="page prose">
        {TERMS.map(([heading, text]) => (
          <section key={heading} className="section-tight">
            <h2>{t(heading)}</h2>
            <p>{t(text)}</p>
          </section>
        ))}
        <section className="section-tight">
          <h2>{t("Contact")}</h2>
          <p>
            {t("For corrections and takedowns, use the form on the corrections page. For anything else, reply to any message from Qayem.")}{" "}
            <Link to="/corrections">{t("Corrections and takedowns")}</Link>
            {" · "}
            <Link to="/privacy">{t("Privacy")}</Link>
          </p>
          <p className="fineprint">{t("Last updated 22 November 2026.")}</p>
        </section>
      </div>
    </div>
  );
}

type Kind = "correction" | "takedown";

export function Corrections() {
  const [params] = useSearchParams();
  const config = useGrowthConfig();
  const [kind, setKind] = useState<Kind>(params.get("kind") === "takedown" ? "takedown" : "correction");
  const [url, setUrl] = useState(params.get("url") ?? "");
  const [issue, setIssue] = useState("");
  return (
    <div className="page-enter">
      <header className="page-head">
        <div className="page">
          <span className="eyebrow">{t("Corrections and takedowns")}</span>
          <h1 className="display">{t("Tell us what is wrong")}</h1>
          <p className="lede">
            {t("A wrong figure, a listing that is not what it says, or something about you or your listing that should not be on Qayem: send the page and what is wrong, and we reply by e-mail.")}
          </p>
        </div>
      </header>
      <div className="page split section-tight corrections">
        <div className="prose">
          <h2>{t("What happens next")}</h2>
          <ol>
            <li>{t("We read every request, usually within two working days.")}</li>
            <li>{t("A wrong figure is checked against the listings behind it and corrected, with the page’s date updated.")}</li>
            <li>{t("A takedown removes the listing or detail from Qayem; figures built from many listings stay, without it.")}</li>
            <li>{t("We reply to the e-mail address you give, and use it for nothing else.")}</li>
          </ol>
          <p className="fineprint">
            <Link to="/terms">{t("Terms of use")}</Link>
            {" · "}
            <Link to="/privacy">{t("Privacy")}</Link>
          </p>
        </div>
        <section className="capture capture-alert" aria-labelledby="correction-form">
          <div className="capture-head">
            <span className="capture-icon">
              <FileWarning size={20} />
            </span>
            <div>
              <h3 id="correction-form">{t(kind === "takedown" ? "Ask for a takedown" : "Report a mistake")}</h3>
              <p>{t("An e-mail address is needed so we can reply.")}</p>
            </div>
          </div>
          {!config ? null : config.leads ? (
            <CaptureForm
              cta={kind === "takedown" ? "Send the takedown request" : "Send the correction"}
              emailOnly
              roles={false}
              validate={() => (issue.trim().length < 5 ? "Say what is wrong, in a few words." : null)}
              send={lead(kind, () => ({ intent: { url: url.trim().slice(0, 300), issue: issue.trim().slice(0, 1000) } }))}
              done={
                <p>
                  <CheckCircle2 size={17} /> {t("Received. We will reply by e-mail, usually within two working days.")}
                </p>
              }
            >
              <div className="segmented" role="group" aria-label={t("What do you need?")}>
                <button type="button" aria-pressed={kind === "correction"} onClick={() => setKind("correction")}>
                  {t("A correction")}
                </button>
                <button type="button" aria-pressed={kind === "takedown"} onClick={() => setKind("takedown")}>
                  {t("A takedown")}
                </button>
              </div>
              <label className="field">
                <span className="field-label">{t("The page’s address (optional)")}</span>
                <span className="input">
                  <input
                    type="url"
                    inputMode="url"
                    dir="ltr"
                    value={url}
                    onChange={(event) => setUrl(event.target.value)}
                    placeholder="https://qayem.ai/…"
                    maxLength={300}
                  />
                </span>
              </label>
              <label className="field">
                <span className="field-label">{t("What is wrong")}</span>
                <span className="input input-area">
                  <textarea value={issue} onChange={(event) => setIssue(event.target.value)} rows={4} maxLength={1000} required />
                </span>
              </label>
            </CaptureForm>
          ) : (
            <p className="muted">{t("The form is not open yet. Please try again later.")}</p>
          )}
        </section>
      </div>
    </div>
  );
}
