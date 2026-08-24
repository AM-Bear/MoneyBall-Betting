---
name: Shared route metadata
description: The single-source rule for MONEYLINE route SEO, static output, and browser head updates.
---

# Shared route metadata

**Rule:** Treat the MONEYLINE route SEO JSON as the sole authority for titles, descriptions, canonical paths, indexing directives, legacy aliases, and public route eligibility. Backend rendering, static route generation, browser updates, and sitemap selection must resolve it rather than define local copies.

**Why:** Separate frontend and backend registries previously sent contradictory canonical URLs and page descriptions for the same research routes, splitting search signals and social previews.

**How to apply:** When adding or changing a public route, update the shared source and keep aliases mapped to the canonical research family. Run the server metadata tests and production frontend smoke gate so both pre-hydration and hydrated document heads are checked.