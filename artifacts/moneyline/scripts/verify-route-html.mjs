import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const artifactDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const distDir = path.join(artifactDir, "dist", "public");
const config = JSON.parse(await readFile(path.join(artifactDir, "seo-config.json"), "utf8"));
const siteUrl = config.siteUrl.replace(/\/+$/, "");

function requireMarkup(markup, value, routePath, label) {
  if (!markup.includes(value)) {
    throw new Error(`Generated ${routePath} HTML is missing shared ${label}.`);
  }
}

let checkedCount = 0;
for (const [routePath, metadata] of Object.entries(config.routes)) {
  if (!metadata.public) continue;
  const outputPath = routePath === "/"
    ? path.join(distDir, "index.html")
    : path.join(distDir, routePath.slice(1), "index.html");
  const markup = await readFile(outputPath, "utf8");
  const canonical = `${siteUrl}${metadata.canonicalPath === "/" ? "" : metadata.canonicalPath}`;
  const robots = metadata.indexable ? "index, follow" : "noindex, follow";

  requireMarkup(markup, `<title data-seo="title" data-seo-title>${metadata.title}</title>`, routePath, "title");
  requireMarkup(markup, `content="${metadata.description}"`, routePath, "description");
  requireMarkup(markup, `content="${robots}"`, routePath, "robots value");
  requireMarkup(markup, `content="${canonical}"`, routePath, "Open Graph URL");
  requireMarkup(markup, `href="${canonical}"`, routePath, "canonical URL");
  checkedCount += 1;
}

console.log(`Verified shared metadata in ${checkedCount} generated public routes.`);