import { t } from "../locale";

const SECTIONS: [string, string][] = [
  [
    "Browsing is anonymous",
    "Every comparison is open without an account. To learn which pages help, Qayem counts visits itself: the page, the country, the kind of device and a random ID kept in your browser. No cookies, no advertising trackers, and no IP addresses are stored.",
  ],
  [
    "What we keep when you ask for something",
    "When you ask for an alert, a checklist, a developer’s prices or a sheet, we keep the WhatsApp number or e-mail you give, your name if you give it, and what you asked about (the unit, compound or search). We use it only to answer that request.",
  ],
  [
    "Brokers never get your number without your permission",
    "We do not sell or pass on your details. If you ask to be put in touch with a developer or an adviser, we ask you first, every time.",
  ],
  [
    "Listings carry no one’s details",
    "Qayem reads public listings for their facts only: price, area, type, payment plan, place and date. It never keeps a seller’s or broker’s name, phone number or photos, and shows no source’s photos.",
  ],
  [
    "Comparisons, not advice",
    "Qayem’s figures are asking and contract prices compared by published rules (see the methodology). They are not valuations, offers or investment advice: check every unit and its papers before you pay anything.",
  ],
  [
    "Stopping",
    "Every alert message has a link to stop it. To have your details deleted, reply to any message from us or write to us on WhatsApp, and we delete them.",
  ],
];

export default function Privacy() {
  return (
    <div className="page-enter">
      <header className="page-head">
        <div className="page">
          <span className="eyebrow">{t("Privacy")}</span>
          <h1 className="display">{t("What Qayem keeps, and why")}</h1>
        </div>
      </header>
      <div className="page prose">
        {SECTIONS.map(([heading, text]) => (
          <section key={heading} className="section-tight">
            <h2>{t(heading)}</h2>
            <p>{t(text)}</p>
          </section>
        ))}
      </div>
    </div>
  );
}
