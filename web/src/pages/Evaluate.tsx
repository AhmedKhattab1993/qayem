import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, ChevronDown, Link2, Scale } from "lucide-react";
import { year as formatYear, api, ApiError, classLabel, money, number, percent, titleCase, useApi, useCatalog, sep } from "../lib";
import { t } from "../locale";
import type { Evaluation, Payment } from "../types";
import { ErrorState, Loading } from "../components/States";
import { BreakdownView, PaymentFacts, Unknowns, ValuationSummary } from "../components/Valuation";
import { UnitTable } from "../components/UnitTable";

const FIELDS = [
  "compound",
  "district",
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
  const set = (field: keyof Form, value: string | boolean) => setForm((current) => ({ ...current, [field]: value }));

  const query = useMemo(() => {
    const next = new URLSearchParams();
    for (const field of FIELDS) {
      const value = params.get(field);
      if (value) next.set(field, value);
    }
    return next.get("property_type") && next.get("area") && next.get("price") && (next.get("compound") || next.get("district"))
      ? `/evaluate?${next}`
      : null;
  }, [params]);
  const { data, error, retry } = useApi<Evaluation>(query);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const area = Number(form.area);
    const price = Number(form.price);
    const down = Number(form.down_payment);
    if (!form.compound.trim() && !form.district) return setProblem("Choose a compound, or a district if the unit is not in one.");
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
  };

  const types = catalog?.property_types ?? [];

  return (
    <div className="evaluate page-enter">
      <header className="page-head">
        <div className="page">
          <span className="eyebrow">{t("Evaluate a unit")}</span>
          <h1 className="display">
            {t("Is this")} <em>{t("a fair price?")}</em>
          </h1>
          <p className="lede">
            {t(
              "Describe the unit you were offered. Qayem converts its payment plan to cash today and prices it against its own compound and developer.",
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
                <datalist id="evaluate-compounds">
                  {catalog?.compounds.map((c) => (
                    <option key={c.key} value={c.name}>
                      {[c.developer, c.district].filter(Boolean).join(sep())}
                    </option>
                  ))}
                </datalist>
              </label>
              <label className="field">
                <span className="field-label">{t("District, if not in a known compound")}</span>
                <span className="select">
                  <select value={form.district} onChange={(event) => set("district", event.target.value)}>
                    <option value="">{t("Choose a district")}</option>
                    {catalog?.districts
                      .filter((d) => d.units >= 5)
                      .map((d) => (
                        <option key={d.key} value={d.name}>
                          {d.name}
                        </option>
                      ))}
                  </select>
                  <ChevronDown size={15} />
                </span>
              </label>
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
              <Scale size={16} /> {t("Value this unit")}
            </button>
          </form>
        )}

        <section className="evaluate-result" aria-live="polite" aria-label={t("Valuation")}>
          {!query ? (
            <div className="evaluate-placeholder">
              <Scale size={28} strokeWidth={1.4} />
              <h2>{t("Your valuation appears here")}</h2>
              <p>
                {t(
                  "You will see a fair cash value with a likely range, what the payment plan is worth today, how the value was built, and the comparable listings behind it.",
                )}
              </p>
            </div>
          ) : error ? (
            <ErrorState message={error} retry={retry} />
          ) : !data ? (
            <Loading label="Valuing the unit…" />
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
          <span className="field-label">{t("Paste a link from Nawy, OpenSooq, Aqarmap, Semsar Masr, GPM or Coldwell Banker")}</span>
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

const noteText: Record<string, string> = {
  compound_not_found: "We have no resale listings for that compound, so it is valued at district level.",
  developer_not_found: "We do not recognise that developer.",
  district_not_found: "We have no resale listings in that district.",
};

function Result({ data }: { data: Evaluation }) {
  const { inputs, valuation } = data;
  return (
    <div className="result">
      <div className="result-head">
        <span className="eyebrow no-rule">{t("Valuation")}</span>
        <h2 dir="auto">
          {titleCase(inputs.property_type)}{sep()}{number(inputs.area_m2)} {t("m²")}
        </h2>
        <p className="muted" dir="auto">
          {inputs.compound ? (
            <Link to={`/compounds/${encodeURIComponent(inputs.compound.key)}`}>{inputs.compound.name}</Link>
          ) : (
            t("No compound")
          )}
          {inputs.developer && (
            <>
              {sep()}
              <Link to={`/developers/${encodeURIComponent(inputs.developer.key)}`}>{inputs.developer.name}</Link>
            </>
          )}
          {inputs.district && `${sep()}${inputs.district}`}
        </p>
      </div>
      {data.notes.map((note) => (
        <p key={note} className="notice">
          {t(noteText[note] ?? note)}
        </p>
      ))}
      <ValuationSummary valuation={valuation} price={inputs.price} />
      <section className="result-section">
        <h3>{t("The payment plan, in today’s money")}</h3>
        <PaymentFacts payment={data.payment} price={inputs.price} />
      </section>
      <CostCalculator
        price={inputs.price}
        payment={data.payment}
        fair={valuation.fair_value ?? null}
        ready={inputs.delivery.bucket === "ready"}
      />
      {data.breakdown && (
        <section className="result-section">
          <h3>{t("How the fair value was built")}</h3>
          <BreakdownView breakdown={data.breakdown} cls={inputs.class} />
        </section>
      )}
      <section className="result-section">
        <h3>{t("What this valuation cannot see")}</h3>
        <Unknowns items={data.unknowns} />
        <p className="fineprint">{t("Ask the seller and the developer about each of these before you commit.")}</p>
      </section>
      {data.comparables.length > 0 && (
        <section className="result-section">
          <h3>{t("Closest comparable listings")}</h3>
          <p className="muted">{t("Same class of unit, nearest in size, from the same compound where possible. {cls}.", { cls: classLabel(inputs.class) })}</p>
          <UnitTable items={data.comparables} caption="Comparable listings" />
        </section>
      )}
    </div>
  );
}

const DEFAULTS = { transfer: 5, brokerage: 2.5, maintenance: 8, registration: 0 };

/** All-in cost of buying: what leaves your account now, later, and in today’s money. */
function CostCalculator({ price, payment, fair, ready }: { price: number; payment: Payment; fair: number | null; ready: boolean }) {
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
          <dd className="num">{money(later)}</dd>
        </div>
        <div className="cost-today">
          <dt>{t("All-in cost in today’s money")}</dt>
          <dd className="num">{money(today)}</dd>
        </div>
        {fair != null && (
          <div>
            <dt>{t("Fair value plus the same fees")}</dt>
            <dd className="num">
              {money(fair + fees + fee("maintenance"))}
              <small className="muted">{sep()}{t("fees {share}", { share: percent((fees + fee("maintenance")) / price, 1) })}</small>
            </dd>
          </div>
        )}
      </dl>
    </section>
  );
}
