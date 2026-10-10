import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, ChevronDown, Link2, Scale } from "lucide-react";
import { year as formatYear, api, ApiError, money, number, percent, quarterly, titleCase, useApi, useCatalog, scrollBehavior, sep, nameOf, place } from "../lib";
import { t } from "../locale";
import type { Evaluation, Payment } from "../types";
import { ErrorState, Loading } from "../components/States";
import { OpportunitySummary, PaymentFacts, PeerPanel, Unknowns } from "../components/Opportunity";
import { DeveloperPrice } from "../components/DeveloperPrice";
import { Comparables } from "../components/UnitTable";
import { NameList } from "../components/Names";

const FIELDS = [
  "compound",
  "property_type",
  "area",
  "price",
  "down_payment",
  "installment_years",
  "delivery",
  "finishing",
] as const;
type Form = Record<(typeof FIELDS)[number], string> & { plan: boolean };
const thisYear = new Date().getFullYear();
const years = Array.from({ length: 8 }, (_, i) => String(thisYear + i));

function fromParams(params: URLSearchParams): Form {
  const form = { ...Object.fromEntries(FIELDS.map((f) => [f, params.get(f) ?? ""])), plan: false } as Form;
  form.plan = Boolean(form.down_payment || form.installment_years);
  if (!form.property_type) form.property_type = "apartment";
  return form;
}

export default function Evaluate() {
  const [params, setParams] = useSearchParams();
  const catalog = useCatalog();
  const [mode, setMode] = useState(params.get("mode") === "link" ? "link" : "describe");
  const [form, setForm] = useState<Form>(() => fromParams(params));
  const [problem, setProblem] = useState("");
  const result = useRef<HTMLElement>(null);
  const set = (field: keyof Form, value: string | boolean) => setForm((current) => ({ ...current, [field]: value }));

  const query = useMemo(() => {
    const next = new URLSearchParams();
    for (const field of FIELDS) {
      const value = params.get(field);
      if (value) next.set(field, value);
    }
    return next.get("property_type") && next.get("area") && next.get("price") && next.get("compound")
      ? `/evaluate?${next}`
      : null;
  }, [params]);
  const { data, error, retry } = useApi<Evaluation>(query);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const area = Number(form.area);
    const price = Number(form.price);
    const down = Number(form.down_payment);
    if (!form.compound.trim()) return setProblem("Choose the unit’s compound: every comparison is within its compound.");
    if (!(area >= 20 && area <= 5000)) return setProblem("Enter an area between 20 and 5,000 m².");
    if (!(price >= 100_000)) return setProblem("Enter the full headline price in EGP.");
    if (form.plan && !(down >= 0 && down <= price)) return setProblem("The amount paid at signing must be between 0 and the headline price.");
    if (form.plan && !(Number(form.installment_years) > 0)) return setProblem("Enter how many years of installments remain.");
    setProblem("");
    const next = new URLSearchParams();
    for (const field of FIELDS) {
      if ((field === "down_payment" || field === "installment_years") && !form.plan) continue;
      const value = String(form[field]).trim();
      if (value) next.set(field, value);
    }
    setParams(next);
    // On a phone the result sits below the form: take the reader to it.
    if (window.matchMedia("(max-width: 900px)").matches)
      requestAnimationFrame(() => result.current?.scrollIntoView({ behavior: scrollBehavior(), block: "start" }));
  };

  const types = catalog?.property_types ?? [];

  return (
    <div className="evaluate page-enter">
      <header className="page-head">
        <div className="page">
          <span className="eyebrow">{t("Compare a unit")}</span>
          <h1 className="display">
            {t("Is this")} <em>{t("a real opportunity?")}</em>
          </h1>
          <p className="lede">
            {t(
              "Describe the unit you were offered. Qayem puts its payment plan in today’s money and compares it with the developer’s price today and the similar units listed in the same compound.",
            )}
          </p>
          <div className="segmented" role="group" aria-label={t("How to evaluate")}>
            <button aria-pressed={mode === "describe"} onClick={() => setMode("describe")}>
              {t("Describe the unit")}
            </button>
            <button aria-pressed={mode === "link"} onClick={() => setMode("link")}>
              <Link2 size={14} /> {t("Paste a listing link")}
            </button>
          </div>
        </div>
      </header>

      <div className="page evaluate-body">
        {mode === "link" ? (
          <LinkLookup onFallback={() => setMode("describe")} />
        ) : (
          <form className="evaluate-form" onSubmit={submit} noValidate>
            <fieldset>
              <legend>{t("Where")}</legend>
              <label className="field">
                <span className="field-label">{t("Compound")}</span>
                <span className="input">
                  <input
                    value={form.compound}
                    onChange={(event) => set("compound", event.target.value)}
                    list="evaluate-compounds"
                    placeholder={t("Start typing a compound name")}
                    maxLength={200}
                  />
                </span>
              </label>
              {/* Outside the label: option text would otherwise become the field's accessible name. */}
              <datalist id="evaluate-compounds">
                {catalog?.compounds.map((c) => (
                  <option key={c.key} value={c.name}>
                    {[c.name_ar, c.developer, place(c.district)].filter(Boolean).join(sep())}
                  </option>
                ))}
              </datalist>
            </fieldset>
            <fieldset>
              <legend>{t("The unit")}</legend>
              <div className="form-row">
                <label className="field">
                  <span className="field-label">{t("Unit type")}</span>
                  <span className="select">
                    <select value={form.property_type} onChange={(event) => set("property_type", event.target.value)}>
                      {(types.length ? types : [{ value: "apartment", class: "apartment", count: 0 }]).map((type) => (
                        <option key={type.value} value={type.value}>
                          {titleCase(type.value)}
                        </option>
                      ))}
                    </select>
                    <ChevronDown size={15} />
                  </span>
                </label>
                <label className="field">
                  <span className="field-label">{t("Area (m²)")}</span>
                  <span className="input">
                    <input
                      inputMode="decimal"
                      type="number"
                      min={20}
                      max={5000}
                      value={form.area}
                      onChange={(event) => set("area", event.target.value)}
                      required
                    />
                  </span>
                </label>
              </div>
              <div className="form-row">
                <label className="field">
                  <span className="field-label">{t("Finishing")}</span>
                  <span className="select">
                    <select value={form.finishing} onChange={(event) => set("finishing", event.target.value)}>
                      <option value="">{t("Not sure")}</option>
                      {["core_shell", "semi_finished", "finished", "furnished"].map((value) => (
                        <option key={value} value={value}>
                          {titleCase(value)}
                        </option>
                      ))}
                    </select>
                    <ChevronDown size={15} />
                  </span>
                </label>
                <label className="field">
                  <span className="field-label">{t("Delivery")}</span>
                  <span className="select">
                    <select value={form.delivery} onChange={(event) => set("delivery", event.target.value)}>
                      <option value="">{t("Not sure")}</option>
                      <option value="ready">{t("Ready now")}</option>
                      {years.map((year) => (
                        <option key={year} value={year}>
                          {t("In {year}", { year: formatYear(year) })}
                        </option>
                      ))}
                    </select>
                    <ChevronDown size={15} />
                  </span>
                </label>
              </div>
            </fieldset>
            <fieldset>
              <legend>{t("The price")}</legend>
              <label className="field">
                <span className="field-label">{t("Headline price (EGP)")}</span>
                <span className="input">
                  <input
                    inputMode="numeric"
                    type="number"
                    min={100000}
                    value={form.price}
                    onChange={(event) => set("price", event.target.value)}
                    required
                  />
                </span>
                {Number(form.price) >= 100_000 && <small className="muted num">{money(Number(form.price))}</small>}
              </label>
              <div className="segmented" role="group" aria-label={t("Payment")}>
                <button type="button" aria-pressed={!form.plan} onClick={() => set("plan", false)}>
                  {t("Cash")}
                </button>
                <button type="button" aria-pressed={form.plan} onClick={() => set("plan", true)}>
                  {t("Installments")}
                </button>
              </div>
              {form.plan && (
                <div className="form-row">
                  <label className="field">
                    <span className="field-label">{t("Paid at signing (EGP)")}</span>
                    <span className="input">
                      <input
                        inputMode="numeric"
                        type="number"
                        min={0}
                        value={form.down_payment}
                        onChange={(event) => set("down_payment", event.target.value)}
                      />
                    </span>
                    <small className="muted">{t("Overpayment plus the down payment already paid to the developer")}</small>
                  </label>
                  <label className="field">
                    <span className="field-label">{t("Years of installments left")}</span>
                    <span className="input">
                      <input
                        inputMode="decimal"
                        type="number"
                        min={0.25}
                        max={15}
                        step={0.25}
                        value={form.installment_years}
                        onChange={(event) => set("installment_years", event.target.value)}
                      />
                    </span>
                  </label>
                </div>
              )}
            </fieldset>
            {problem && (
              <p className="field-error" role="alert">
                {t(problem)}
              </p>
            )}
            <button type="submit" className="btn btn-ink btn-block">
              <Scale size={16} /> {t("Compare this unit")}
            </button>
          </form>
        )}

        <section className="evaluate-result" ref={result} aria-live="polite" aria-label={t("Comparison")}>
          {!query ? (
            <div className="evaluate-placeholder">
              <Scale size={28} strokeWidth={1.4} />
              <h2>{t("Your comparison appears here")}</h2>
              <p>
                {t(
                  "You will see how the unit compares with the developer’s price today and with the similar units listed in its compound, what its payment plan is worth today, and the units behind the comparison.",
                )}
              </p>
            </div>
          ) : error ? (
            <ErrorState message={error} retry={retry} />
          ) : !data ? (
            <Loading label="Comparing the unit…" />
          ) : (
            <Result data={data} />
          )}
        </section>
      </div>
    </div>
  );
}

function LinkLookup({ onFallback }: { onFallback: () => void }) {
  const navigate = useNavigate();
  const [url, setUrl] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "missing">("idle");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!url.trim()) return;
    setState("busy");
    try {
      const { id } = await api<{ id: number }>(`/lookup?url=${encodeURIComponent(url.trim())}`);
      navigate(`/units/${id}`);
    } catch (error) {
      setState(error instanceof ApiError && error.status === 404 ? "missing" : "idle");
    }
  };
  return (
    <form className="evaluate-form" onSubmit={submit}>
      <fieldset>
        <legend>{t("Listing link")}</legend>
        <label className="field">
          <span className="field-label">{t("Paste an AqarExit unit link")}</span>
          <span className="input">
            <Link2 size={17} />
            <input
              type="url"
              inputMode="url"
              value={url}
              onChange={(event) => {
                setUrl(event.target.value);
                setState("idle");
              }}
              placeholder="https://"
              dir="ltr"
            />
          </span>
        </label>
      </fieldset>
      {state === "missing" && (
        <div className="notice" role="alert">
          <p>{t("We have not indexed that listing link. Enter its details instead.")}</p>
          <button type="button" className="btn btn-sm" onClick={onFallback}>
            {t("Describe the unit")}
          </button>
        </div>
      )}
      <button type="submit" className="btn btn-ink btn-block" disabled={state === "busy"}>
        {t("Find this listing")} <ArrowRight size={16} className="flip-rtl" />
      </button>
    </form>
  );
}

function Result({ data }: { data: Evaluation }) {
  const { inputs } = data;
  return (
    <div className="result">
      <div className="result-head">
        <span className="eyebrow no-rule">{t("Comparison")}</span>
        <h2>
          {titleCase(inputs.property_type)}{sep()}{number(inputs.area_m2)} {t("m²")}
        </h2>
        <p className="muted">
          <NameList
            items={[
              inputs.compound ? (
                <Link to={`/compounds/${encodeURIComponent(inputs.compound.key)}`}>{nameOf(inputs.compound)}</Link>
              ) : (
                t("No compound")
              ),
              inputs.developer && (
                <Link to={`/developers/${encodeURIComponent(inputs.developer.key)}`}>{nameOf(inputs.developer)}</Link>
              ),
              place(inputs.district),
            ]}
          />
        </p>
      </div>
      {data.status === "compound_not_found" ? (
        <p className="notice">
          {t("We have no resale listings in that compound, so there is nothing to compare it with. Check the spelling, or choose a compound from the list.")}
        </p>
      ) : (
        <>
          <OpportunitySummary unit={data} />
          <CostCalculator price={inputs.price} payment={data.payment} ready={inputs.delivery?.bucket === "ready"} />
          {data.launch && (
            <section className="result-section">
              <h3>{t("Against the developer’s price today")}</h3>
              <DeveloperPrice
                unit={{ launch: data.launch, payment: data.payment, price: inputs.price, finishing_class: inputs.finishing_class }}
              />
            </section>
          )}
          {data.peers && (
            <section className="result-section">
              <h3>{t("Against similar units listed now")}</h3>
              <PeerPanel peers={data.peers} price_per_m2={inputs.price_per_m2} />
            </section>
          )}
        </>
      )}
      <section className="result-section">
        <h3>{t("The payment plan, in today’s money")}</h3>
        <PaymentFacts payment={data.payment} price={inputs.price} />
      </section>
      {data.status === "compound_not_found" && (
        <CostCalculator price={inputs.price} payment={data.payment} ready={inputs.delivery?.bucket === "ready"} />
      )}
      {data.status === "compared" && (
        <section className="result-section">
          <h3>{t("What this comparison cannot see")}</h3>
          {/* The fees are assumptions entered in the cost above; they are confirmed there, not repeated here. */}
          <Unknowns items={data.unknowns.filter((item) => !CALCULATED.includes(item))} />
          <p className="fineprint">{t("Ask the seller and the developer about each of these before you commit.")}</p>
        </section>
      )}
      {data.comparables.length > 0 && (
        <section className="result-section">
          <h3>{t("Similar units listed now")}</h3>
          <p className="muted">{t("Same compound and unit type, nearest in size first.")}</p>
          <Comparables items={data.comparables} caption="Similar units" />
        </section>
      )}
    </div>
  );
}

const DEFAULTS = { transfer: 5, brokerage: 2.5, maintenance: 8, registration: 0 };
/** Unknowns the cost calculator asks about. */
const CALCULATED = ["transfer_fee", "maintenance_deposit"];

/** All-in cost of buying: what leaves your account now, later, and in today’s money. */
function CostCalculator({ price, payment, ready }: { price: number; payment: Payment; ready: boolean }) {
  const [rates, setRates] = useState({ ...DEFAULTS, maintenance: ready ? 0 : DEFAULTS.maintenance });
  useEffect(() => setRates((current) => ({ ...current, maintenance: ready ? 0 : DEFAULTS.maintenance })), [ready]);
  const fee = (key: keyof typeof DEFAULTS) => (price * rates[key]) / 100;
  const signing = price - (payment.remaining ?? 0);
  const fees = fee("transfer") + fee("brokerage") + fee("registration");
  const later = (payment.remaining ?? 0) + fee("maintenance");
  const today = (payment.cash_equivalent ?? price) + fees + fee("maintenance");
  const field = (key: keyof typeof DEFAULTS, label: string, hint: string) => (
    <label className="field">
      <span className="field-label">{t(label)}</span>
      <span className="input input-suffix">
        <input
          type="number"
          inputMode="decimal"
          min={0}
          max={20}
          step={0.5}
          value={rates[key]}
          onChange={(event) => setRates((current) => ({ ...current, [key]: Math.max(0, Number(event.target.value) || 0) }))}
        />
        <span>%</span>
      </span>
      <small className="muted">{t(hint)}</small>
    </label>
  );
  return (
    <section className="result-section cost">
      <h3>{t("Total cost of buying")}</h3>
      <p className="muted">
        {t("Fees differ by developer and deal. These are editable assumptions, as a share of the headline price.")}
      </p>
      <div className="cost-inputs">
        {field("transfer", "Developer transfer fee", "Charged by the developer to move the contract to you")}
        {field("brokerage", "Brokerage", "If a broker is involved")}
        {field("maintenance", "Maintenance deposit", "Often due at handover if the seller has not paid it")}
        {field("registration", "Registration", "Only if you register the title")}
      </div>
      <dl className="cost-totals">
        <div>
          <dt>{t("Cash needed at signing")}</dt>
          <dd className="num">{money(signing + fees)}</dd>
        </div>
        <div>
          <dt>{t("Paid later")}</dt>
          <dd className="num">
            {money(later)}
            {quarterly(payment) != null && (
              <small className="muted cost-each">{t("≈ {amount} a quarter", { amount: money(quarterly(payment)) })}</small>
            )}
          </dd>
        </div>
        <div className="cost-today">
          <dt>{t("All-in cost in today’s money")}</dt>
          <dd className="num">{money(today)}</dd>
        </div>
        <div>
          <dt>{t("Fees as a share of the price")}</dt>
          <dd className="num">{percent((fees + fee("maintenance")) / price, 1)}</dd>
        </div>
      </dl>
      <p className="fineprint">
        {t("Ask the developer for its transfer fee, and the seller whether the maintenance deposit is already paid.")}
      </p>
    </section>
  );
}
