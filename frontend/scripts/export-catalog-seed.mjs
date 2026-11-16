import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { basename, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// One-time, explicit export of repository fixtures, never browser user state.
const require = createRequire(import.meta.url);
const ts = require("typescript");
const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = readFileSync(
  resolve(frontend, "src/preview/fixtures.ts"),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const { previewHeritages, previewContentSources } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`
);

const items = previewHeritages.map((heritage) => ({
  heritage_id: heritage.id,
  name: heritage.name,
  slug: heritage.slug,
  province: heritage.province,
  address: heritage.address,
  category: heritage.category,
  period: heritage.period,
  summary: heritage.introduction,
  historical_information: heritage.history,
  cultural_information: heritage.culturalValue,
  tags: heritage.tags,
  content_status: heritage.publicationStatus,
  illustrative: true,
  location: heritage.coordinates
    ? {
        latitude: heritage.coordinates.latitude,
        longitude: heritage.coordinates.longitude,
        verification_status: "illustrative",
        verification_note: heritage.coordinates.verificationNote,
        source_id: null,
      }
    : null,
  media: heritage.media.map((media) => {
    if (
      !existsSync(resolve(frontend, `public/${media.url.replace(/^\//, "")}`))
    )
      throw new Error(`Missing repository image for ${heritage.id}`);
    return {
      media_id: media.id,
      kind: "image",
      storage_key: basename(media.url),
      alt: media.alt,
      caption: media.caption,
      verified: false,
    };
  }),
  information_sources: previewContentSources
    .filter((source) => heritage.sourceIds.includes(source.id))
    .map((source) => ({
      source_id: source.id,
      title: source.title,
      publisher: source.publisher,
      url: source.url,
      kind: source.kind,
      summary: source.summary,
      verified: source.verified,
      verification_note: source.verificationNote,
      index_status: "not_indexed",
    })),
}));
const output = resolve(frontend, "../samples/catalog/heritages.json");
mkdirSync(dirname(output), { recursive: true });
writeFileSync(
  output,
  JSON.stringify(
    {
      schema_version: 1,
      provenance:
        "Repository UI Preview fixtures; illustrative records and coordinates, not verified historical data or an indexed RAG corpus.",
      items,
    },
    null,
    2,
  ) + "\n",
);
console.log(
  JSON.stringify({
    records: items.length,
    published: items.filter((item) => item.content_status === "published")
      .length,
    output,
  }),
);
