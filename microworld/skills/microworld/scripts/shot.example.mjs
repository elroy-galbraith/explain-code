// Worked example: screenshot pass pattern, originally written against
// docs/microworlds/automl-openevolve-seeding.html.
// The browser/context/theme boilerplate is shared (screenshot-helpers.mjs);
// only the step list below (what to click/evaluate before each shot) is
// specific to this world's UI. Adapt it for each new micro-world.
// Run from the repo root, with <name> and the output directory replaced for your build.
import path from "node:path";
import { shootBothThemes } from "./screenshot-helpers.mjs";

const url = "file://" + path.resolve("docs/microworlds/<name>.html");
const out = path.resolve("tmp-screenshots");

// TODO: update step indices below for this build — go(8)/go(15)/etc. are
// specific to automl-openevolve-seeding.html's own step count and phases.
await shootBothThemes(url, out, [
  { name: "1-briefing" },
  { click: "#brief-close", name: "2-mission" },
  { evaluate: () => go(8), name: "3-automl" },               // mid-AutoML
  { evaluate: () => go(15), name: "4-seed" },                 // seed decision
  { evaluate: () => go(20), name: "5-gen5", fullPage: true }, // gen 5 (simple seed: KNN corrected)
  { evaluate: () => go(19), name: "6-fail", fullPage: true }, // gen 4 — the failure
  { evaluate: () => go(31), name: "7-final", fullPage: true },// verdict
  { evaluate: () => openCompare(), name: "8-compare", fullPage: true },
]);
console.log("done");
