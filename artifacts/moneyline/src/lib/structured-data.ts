import { createElement } from "react";

export const SITE_URL = "https://money-ball-betting.replit.app";
export const SITE_NAME = "MONEYLINE";
export const SITE_DESCRIPTION =
  "A transparent baseball statistical research desk for team pricing, matchup edges, model track records, and paper bankroll analysis.";
export const LOGO_URL = `${SITE_URL}/favicon.svg`;

export function siteUrl(path = "/") {
  return `${SITE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export const websiteStructuredData = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "WebSite",
      "@id": `${SITE_URL}/#website`,
      url: siteUrl(),
      name: SITE_NAME,
      alternateName: "MONEYLINE — Moneyball Trading Desk",
      description: SITE_DESCRIPTION,
      publisher: { "@id": `${SITE_URL}/#organization` },
      inLanguage: "en",
    },
    {
      "@type": "Organization",
      "@id": `${SITE_URL}/#organization`,
      name: SITE_NAME,
      url: siteUrl(),
      logo: {
        "@type": "ImageObject",
        url: LOGO_URL,
        contentUrl: LOGO_URL,
        width: 180,
        height: 180,
      },
      description: SITE_DESCRIPTION,
    },
  ],
};

export type ResearchDestination = {
  href: string;
  label: string;
  description: string;
};

export function researchHubStructuredData(
  destinations: ResearchDestination[],
) {
  return {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    "@id": `${SITE_URL}/research#webpage`,
    url: siteUrl("/research"),
    name: "Research | MONEYLINE",
    description:
      "Baseball research surfaces for players, matchups, season outlook, and wire context.",
    isPartOf: { "@id": `${SITE_URL}/#website` },
    publisher: { "@id": `${SITE_URL}/#organization` },
    about: {
      "@type": "Thing",
      name: "Baseball statistical research",
    },
    mainEntity: {
      "@type": "ItemList",
      name: "MONEYLINE research destinations",
      itemListOrder: "https://schema.org/ItemListOrderAscending",
      numberOfItems: destinations.length,
      itemListElement: destinations.map((destination, index) => ({
        "@type": "ListItem",
        position: index + 1,
        name: destination.label,
        description: destination.description,
        url: siteUrl(destination.href),
      })),
    },
  };
}

export const trackRecordStructuredData = {
  "@context": "https://schema.org",
  "@type": "WebPage",
  "@id": `${SITE_URL}/track-record#webpage`,
  url: siteUrl("/track-record"),
  name: "Track record | MONEYLINE",
  description:
    "A public MONEYLINE record showing live grading, starter-adjusted grading, paper parlays, and historical simulation as separate views.",
  isPartOf: { "@id": `${SITE_URL}/#website` },
  publisher: { "@id": `${SITE_URL}/#organization` },
  about: {
    "@type": "Thing",
    name: "Baseball model track record",
  },
};

export function StructuredData({ data }: { data: unknown }) {
  return createElement(
    "script",
    { type: "application/ld+json" },
    JSON.stringify(data),
  );
}