// design/build.mjs: the design system's generated files, built from design/tokens.json (Design Tokens Format Module
// 2025.10) with Node alone, no package. Written by `aidd new design-system`; change it in its own change.
//
//   node design/build.mjs           writes the files below
//   node design/build.mjs --check   writes nothing; exits 1 naming each file that differs (the drift test), 2 on a bad
//                                   tokens file
//
//   design/tokens.css          every token but the colours, as CSS custom properties on :root; durations 0ms under
//                              prefers-reduced-motion
//   design/themes/<theme>.css  one preset per theme set: the roles of color.<theme> as --color-<role>; light (or the
//                              first set) on :root, dark also under prefers-color-scheme until a data-theme is picked
//   DESIGN.md                  its front matter between the two marker lines below: the design.md mirror of the tokens
//
// The convention: raw colours are tokens directly under `color`, never emitted; each group under `color` is a theme
// set, and every set has the same role names. Screens read roles only (var(--color-accent)).
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = dirname(here);
const BEGIN = "# generated from design/tokens.json by design/build.mjs: never edit by hand";
const END = "# end generated";
const HEADER = "/* Generated from design/tokens.json by design/build.mjs: never edit by hand. */\n";

// Read as LF text: a Windows checkout (core.autocrlf) holds CRLF files, and a line ending is no drift.
const readText = (path) => readFileSync(path, "utf8").replaceAll("\r\n", "\n");

function fail(message) {
  console.error(`design/build.mjs: ${message}`);
  process.exit(2);
}

const tree = JSON.parse(readFileSync(join(here, "tokens.json"), "utf8"));

// Every token as { path, value, type }, the type inherited from its group.
function* walk(node, path = [], type = undefined) {
  const own = node.$type ?? type;
  if ("$value" in node) {
    yield { path, value: node.$value, type: own };
    return;
  }
  for (const [key, child] of Object.entries(node)) {
    if (!key.startsWith("$") && child && typeof child === "object") yield* walk(child, [...path, key], own);
  }
}
const all = new Map([...walk(tree)].map((t) => [t.path.join("."), t]));

function resolve(value) {
  for (let hops = 0; typeof value === "string" && /^\{[^{}]+\}$/.test(value); hops++) {
    const target = all.get(value.slice(1, -1));
    if (!target || hops > 32) fail(`${value} resolves to no token`);
    value = target.value;
  }
  return value;
}

const byte = (x) => Math.round(x * 255).toString(16).padStart(2, "0");
function colour(v) {
  const alpha = v.alpha !== undefined && v.alpha < 1;
  if (v.colorSpace === "srgb") return `#${v.components.map(byte).join("")}${alpha ? byte(v.alpha) : ""}`;
  const fn = ["hsl", "hwb", "lab", "lch", "oklab", "oklch"].includes(v.colorSpace) ? v.colorSpace : `color(${v.colorSpace}`;
  const body = `${v.components.join(" ")}${alpha ? ` / ${v.alpha}` : ""}`;
  return fn.startsWith("color(") ? `${fn} ${body})` : `${fn}(${body})`;
}
const family = (v) => (Array.isArray(v) ? v : [v]).map((f) => (/\s/.test(f) ? `"${f}"` : f)).join(", ");
const size = (v) => `${v.value}${v.unit}`;

function css(value, type, where) {
  const v = resolve(value);
  switch (type) {
    case "color":
      return colour(v);
    case "dimension":
    case "duration":
      return size(v);
    case "fontFamily":
      return family(v);
    case "fontWeight":
    case "number":
      return String(v);
    case "cubicBezier":
      return `cubic-bezier(${v.join(", ")})`;
    case "shadow":
      return (Array.isArray(v) ? v : [v])
        .map((s) => [s.inset ? "inset" : "", ...["offsetX", "offsetY", "blur", "spread"].map((k) => size(resolve(s[k]))), colour(resolve(s.color))].filter(Boolean).join(" "))
        .join(", ");
    case "typography": {
      const [weight, fontSize, fontFamily] = [resolve(v.fontWeight), resolve(v.fontSize), resolve(v.fontFamily)];
      return `${weight} ${size(fontSize)}/${resolve(v.lineHeight)} ${family(fontFamily)}`;
    }
    default:
      return fail(`${where}: no CSS for $type ${type}; add a case to design/build.mjs`);
  }
}

// The theme sets: each group under `color`, all with the same role names.
const colourGroup = tree.color ?? {};
const themes = Object.keys(colourGroup).filter((k) => !k.startsWith("$") && !("$value" in colourGroup[k]));
if (themes.length === 0) fail("no theme set under color (color.light, color.dark)");
const roles = (theme) => [...all.values()].filter((t) => t.path[0] === "color" && t.path[1] === theme && t.path.length === 3);
const names = (theme) => roles(theme).map((t) => t.path[2]).sort();
const primary = themes.includes("light") ? "light" : themes[0];
for (const theme of themes) {
  const want = names(primary), have = names(theme);
  const missing = want.filter((r) => !have.includes(r)), extra = have.filter((r) => !want.includes(r));
  if (missing.length || extra.length) fail(`color.${theme} differs from color.${primary}: ${[...missing.map((r) => `no ${r}`), ...extra.map((r) => `extra ${r}`)].join(", ")}`);
}

const block = (selector, lines, indent = "") => `${indent}${selector} {\n${lines.map((l) => `${indent}  ${l}\n`).join("")}${indent}}\n`;
const out = new Map();

// design/tokens.css: everything but the colours.
const rest = [...all.values()].filter((t) => t.path[0] !== "color");
const durations = rest.filter((t) => t.type === "duration");
out.set(
  "design/tokens.css",
  HEADER +
    block(":root", rest.map((t) => `--${t.path.join("-")}: ${css(t.value, t.type, t.path.join("."))};`)) +
    (durations.length ? `@media (prefers-reduced-motion: reduce) {\n${block(":root", durations.map((t) => `--${t.path.join("-")}: 0ms;`), "  ")}}\n` : ""),
);

// design/themes/<theme>.css: one preset per set.
for (const theme of themes) {
  const vars = roles(theme).map((t) => `--color-${t.path[2]}: ${css(t.value, "color", t.path.join("."))};`);
  const scheme = theme === "light" || theme === "dark" ? [`color-scheme: ${theme};`] : [];
  let text = HEADER;
  if (theme === primary) text += block(`:root,\n:root[data-theme="${theme}"]`, [...vars, ...scheme]);
  else text += block(`:root[data-theme="${theme}"]`, [...vars, ...scheme]);
  if (theme === "dark") text += `@media (prefers-color-scheme: dark) {\n${block(":root:not([data-theme])", [...vars, ...scheme], "  ")}}\n`;
  out.set(`design/themes/${theme}.css`, text);
}

// DESIGN.md: the design.md mirror, only between the markers. design.md has one flat colour set and CSS strings, so
// the primary theme's roles keep their names and another theme's become <role>-<theme>; primary names accent.
const key = (k) => (/^[A-Za-z][\w-]*$/.test(k) ? k : JSON.stringify(k));
const yaml = [BEGIN, "colors:"];
for (const theme of themes) {
  for (const t of roles(theme)) yaml.push(`  ${key(theme === primary ? t.path[2] : `${t.path[2]}-${theme}`)}: ${JSON.stringify(css(t.value, "color", t.path.join(".")))}`);
  if (theme === primary && names(primary).includes("accent") && !names(primary).includes("primary")) yaml.push('  primary: "{colors.accent}"');
}
const typography = rest.filter((t) => t.path[0] === "typography" && t.type === "typography");
if (typography.length) {
  yaml.push("typography:");
  for (const t of typography) {
    const v = resolve(t.value);
    yaml.push(`  ${key(t.path.slice(1).join("-"))}:`, `    fontFamily: ${JSON.stringify(family(resolve(v.fontFamily)).replaceAll('"', ""))}`);
    yaml.push(`    fontSize: ${size(resolve(v.fontSize))}`, `    fontWeight: ${resolve(v.fontWeight)}`, `    lineHeight: ${resolve(v.lineHeight)}`);
    if (v.letterSpacing !== undefined) yaml.push(`    letterSpacing: ${size(resolve(v.letterSpacing))}`);
  }
}
for (const [group, name] of [["radius", "rounded"], ["space", "spacing"]]) {
  const scale = rest.filter((t) => t.path[0] === group && t.type === "dimension");
  if (scale.length) yaml.push(`${name}:`, ...scale.map((t) => `  ${key(t.path.slice(1).join("-"))}: ${size(resolve(t.value))}`));
}
yaml.push(END);
const designPath = join(root, "DESIGN.md");
if (existsSync(designPath)) {
  const text = readText(designPath);
  const start = text.indexOf(`\n${BEGIN}\n`), stop = text.indexOf(`\n${END}\n`);
  if (!text.startsWith("---\n") || start < 0 || stop < start) fail(`DESIGN.md: its front matter needs the lines "${BEGIN}" and "${END}"`);
  out.set("DESIGN.md", `${text.slice(0, start + 1)}${yaml.join("\n")}${text.slice(stop + END.length + 1)}`);
}

const check = process.argv.includes("--check");
const drifted = [...out].filter(([rel, text]) => !existsSync(join(root, rel)) || readText(join(root, rel)) !== text).map(([rel]) => rel);
const themeDir = join(root, "design", "themes");
const stale = existsSync(themeDir) ? readdirSync(themeDir).filter((f) => f.endsWith(".css") && !out.has(`design/themes/${f}`)).map((f) => `design/themes/${f}`) : [];
if (check) {
  for (const rel of drifted) console.log(`drift: ${rel} differs from design/tokens.json; run node design/build.mjs`);
  for (const rel of stale) console.log(`drift: ${rel} has no theme set in design/tokens.json; delete it`);
  if (drifted.length || stale.length) process.exit(1);
  console.log("ok: every generated design file matches design/tokens.json");
} else {
  mkdirSync(themeDir, { recursive: true });
  for (const rel of drifted) writeFileSync(join(root, rel), out.get(rel), "utf8");
  for (const rel of drifted) console.log(`wrote ${rel}`);
  for (const rel of stale) console.log(`stale: ${rel} has no theme set in design/tokens.json; delete it`);
}
