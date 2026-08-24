import seoConfig from "../seo-config.json";

export interface SeoRouteMetadata {
  title: string;
  description: string;
  canonicalPath: string;
  indexable: boolean;
}

const routes = seoConfig.routes as Record<string, SeoRouteMetadata>;

function normalizePathname(pathname: string) {
  const path = pathname.split("?")[0].split("#")[0] || "/";
  if (path === "/") return "/";
  return `/${path.replace(/^\/+|\/+$/g, "")}`;
}

export function getSeoRouteMetadata(pathname: string) {
  return routes[normalizePathname(pathname)] ?? routes["/404"];
}

function absoluteUrl(pathname: string) {
  const configuredUrl = import.meta.env.VITE_SITE_URL;
  const origin = (configuredUrl || window.location.origin || seoConfig.siteUrl).replace(/\/+$/, "");
  const normalizedPath = pathname === "/" ? "" : pathname;
  return `${origin}${normalizedPath}`;
}

function upsertMeta(attribute: "name" | "property", value: string, content: string) {
  let element = document.head.querySelector<HTMLMetaElement>(
    `meta[${attribute}="${value}"]`,
  );
  if (!element) {
    element = document.createElement("meta");
    element.setAttribute(attribute, value);
    document.head.appendChild(element);
  }
  element.content = content;
}

function upsertCanonical(href: string) {
  let element = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (!element) {
    element = document.createElement("link");
    element.rel = "canonical";
    document.head.appendChild(element);
  }
  element.href = href;
}

export function applySeoMetadata(pathname: string) {
  const metadata = getSeoRouteMetadata(pathname);
  const canonicalUrl = absoluteUrl(metadata.canonicalPath);
  const socialImageUrl = absoluteUrl(seoConfig.socialImagePath);

  document.title = metadata.title;
  upsertMeta("name", "description", metadata.description);
  upsertMeta("name", "robots", metadata.indexable ? "index, follow" : "noindex, nofollow");
  upsertMeta("property", "og:title", metadata.title);
  upsertMeta("property", "og:description", metadata.description);
  upsertMeta("property", "og:url", canonicalUrl);
  upsertMeta("property", "og:image", socialImageUrl);
  upsertMeta("property", "og:image:width", "1200");
  upsertMeta("property", "og:image:height", "630");
  upsertMeta("property", "og:image:alt", "MONEYLINE transparent baseball research desk");
  upsertMeta("name", "twitter:title", metadata.title);
  upsertMeta("name", "twitter:description", metadata.description);
  upsertMeta("name", "twitter:image", socialImageUrl);
  upsertMeta("name", "twitter:image:alt", "MONEYLINE transparent baseball research desk");
  upsertCanonical(canonicalUrl);
}