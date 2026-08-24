import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const artifactDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const distDir = path.join(artifactDir, "dist", "public");
const config = JSON.parse(await readFile(path.join(artifactDir, "seo-config.json"), "utf8"));
const templatePath = path.join(distDir, "index.html");
const template = await readFile(templatePath, "utf8");
const siteUrl = (process.env.PUBLIC_SITE_URL || config.siteUrl).replace(/\/+$/, "");
const socialImageUrl = `${siteUrl}${config.socialImagePath}`;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function replaceMarkedTag(html, marker, attribute, value) {
  const markerPattern = new RegExp(
    `<${marker}\\b(?=[^>]*data-seo=["']${attribute}["'])[^>]*>`,
    "i",
  );
  const match = html.match(markerPattern);
  if (!match) throw new Error(`Missing data-seo="${attribute}" ${marker} in index.html`);

  const replacement = match[0].replace(
    marker === "link"
      ? /\bhref=["'][^"']*["']/i
      : /\bcontent=["'][^"']*["']/i,
    `${marker === "link" ? "href" : "content"}="${escapeHtml(value)}"`,
  );
  return html.replace(markerPattern, replacement);
}

function routeHtml(metadata) {
  const canonicalUrl = `${siteUrl}${metadata.canonicalPath === "/" ? "" : metadata.canonicalPath}`;
  let html = template;
  html = html.replace(
    /<title\b[^>]*data-seo=["']title["'][^>]*>.*?<\/title>/i,
    `<title data-seo="title" data-seo-title>${escapeHtml(metadata.title)}</title>`,
  );
  for (const [marker, attribute, value] of [
    ["meta", "description", metadata.description],
    ["meta", "robots", metadata.indexable ? "index, follow" : "noindex, nofollow"],
    ["meta", "og-title", metadata.title],
    ["meta", "og-description", metadata.description],
    ["meta", "og-url", canonicalUrl],
    ["meta", "og-image", socialImageUrl],
    ["meta", "og-image-width", "1200"],
    ["meta", "og-image-height", "630"],
    ["meta", "og-image-alt", "MONEYLINE transparent baseball research desk"],
    ["meta", "twitter-title", metadata.title],
    ["meta", "twitter-description", metadata.description],
    ["meta", "twitter-image", socialImageUrl],
    ["meta", "twitter-image-alt", "MONEYLINE transparent baseball research desk"],
    ["link", "canonical", canonicalUrl],
  ]) {
    html = replaceMarkedTag(html, marker, attribute, value);
  }
  return html;
}

for (const [routePath, metadata] of Object.entries(config.routes)) {
  if (routePath === "/404") continue;
  const outputDir = routePath === "/" ? distDir : path.join(distDir, routePath.slice(1));
  await mkdir(outputDir, { recursive: true });
  await writeFile(path.join(outputDir, "index.html"), routeHtml(metadata));
}

console.log(`Generated route-aware HTML for ${Object.keys(config.routes).length - 1} public routes.`);