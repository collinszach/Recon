#!/usr/bin/env node
// Regression test for the autofill field matcher.
//
// The fixture is not invented: it is every labelled, fillable control on a real
// Rocket Lab Greenhouse application form, captured 2026-09-21. Forty controls,
// five of them actual profile fields. Before the matcher was tiered it filled
// three of the other thirty-five with confidently wrong values — a city into
// "Are you Hispanic/Latino?", a referral source into a start date. Those are the
// cases that matter: a blank field is visible, a wrong one gets submitted.

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "..");
const sandbox = { window: {}, document: undefined, CSS: undefined };
sandbox.window.ReconAutofill = {};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(root, "field-matcher.js"), "utf8"), sandbox);
const ns = sandbox.window.ReconAutofill;

const fixture = JSON.parse(
  fs.readFileSync(path.join(__dirname, "rocketlab-greenhouse.json"), "utf8")
);
const cases = [...fixture.labels, ...fixture._extra];

let failed = 0;
for (const [label, expected] of cases) {
  const got = ns.matchProfileKey(label);
  if (got !== expected) {
    failed++;
    console.log(
      `  FAIL  ${JSON.stringify(label).slice(0, 72)}\n        expected ${expected}, got ${got}`
    );
  }
}

// The specific false positives that prompted the rewrite, asserted by name so a
// future loosening of a pattern names its own casualty.
const REGRESSIONS = [
  ["Are you Hispanic/Latino?", "city", "ethni-CITY"],
  ["Preferred Internship/Co-Op Start Date*", "how_heard", "P-REFERRED"],
  ["Outside of university coursework, what amount of software engineering experience do you have?", "school", "university"],
];
for (const [label, forbidden, why] of REGRESSIONS) {
  const got = ns.matchProfileKey(label);
  if (got === forbidden) {
    failed++;
    console.log(`  FAIL  regression (${why}): ${label.slice(0, 50)} -> ${forbidden}`);
  }
}

// ── option picking ────────────────────────────────────────────────────────────
// Real option lists captured from the forms surveyed on 2026-09-21/22.
const STATES = ["Select One", "Alabama", "Alaska", "California", "North Carolina",
                "South Carolina", "New York"];
const COUNTRIES = ["United States of America", "United Kingdom", "Canada"];
const PHONE_TYPES = ["Select One", "Landline", "Mobile"];
const GM_FIELDS = ["Engineering Mechanics", "Industrial Mechanical Engineering",
                   "Mechanical and Automation Engineering", "Mechanical and Materials Engineering",
                   "Mechanical Engineering", "Mechanical Engineering and Design Innovation"];

const pickCases = [
  // [list, key, profile value, expected option text or null]
  [STATES, "state", "CA", "California"],              // the abbreviation trap
  [STATES, "state", "NC", "North Carolina"],
  [STATES, "state", "California", "California"],
  [COUNTRIES, "country", "United States", "United States of America"],  // unique prefix
  [PHONE_TYPES, "phone_device_type", "Mobile", "Mobile"],
  [GM_FIELDS, "discipline", "Mechanical Engineering", "Mechanical Engineering"],
  // No loose substring: asked for something absent, pick nothing rather than
  // "Industrial Mechanical Engineering".
  [["Engineering Mechanics", "Industrial Mechanical Engineering"], "discipline",
   "Mechanical Engineering", null],
  [STATES, "state", "ZZ", null],
  [STATES, "state", "", null],
];

for (const [list, key, value, expected] of pickCases) {
  const want = ns.expandAlias(key, value);
  const idx = ns.pickOption(list, want);
  const got = idx === -1 ? null : list[idx];
  if (got !== expected) {
    failed++;
    console.log(`  FAIL  pickOption(${key}=${JSON.stringify(value)}) expected ${JSON.stringify(expected)}, got ${JSON.stringify(got)}`);
  }
}
console.log(`field-matcher: ${pickCases.length} option-picking cases OK`);

// ── the iOS port ──────────────────────────────────────────────────────────────
// ios/Recon/AutofillWebView.swift carries its own copy of these rules, inlined as
// a JS string. That copy is the one that drifted: it concatenated id/name into the
// label text and matched /city/ against an input named "hispanic_ethnicity". So
// the same fixture runs against the Swift file's rules, lifted straight out of it.
const swiftPath = path.resolve(root, "..", "ios", "Recon", "AutofillWebView.swift");
if (fs.existsSync(swiftPath)) {
  const swift = fs.readFileSync(swiftPath, "utf8");
  const from = swift.indexOf("const MAP = [");
  const to = swift.indexOf("// React tracks input state");
  if (from === -1 || to === -1 || to < from) {
    failed++;
    console.log("  FAIL  could not lift the rule block out of AutofillWebView.swift");
  } else {
    // Swift multiline string -> JS: undo the source-level backslash escaping.
    const src = swift.slice(from, to).split("\\\\").join("\\");
    const iosMatch = vm.runInNewContext(
      `${src}; (function (t) { return matchKey(t); })`,
      { document: undefined, CSS: undefined, window: {} }
    );
    let drift = 0;
    for (const [label, expected] of cases) {
      const got = iosMatch(label);
      if (got !== expected) {
        drift++;
        console.log(
          `  FAIL  [ios] ${JSON.stringify(label).slice(0, 64)}\n        expected ${expected}, got ${got}`
        );
      }
    }
    failed += drift;
    if (drift === 0) {
      console.log(`field-matcher: iOS port agrees on all ${cases.length} labels`);
    } else {
      console.log(`field-matcher: iOS port has drifted on ${drift} label(s)`);
    }
  }
} else {
  console.log("field-matcher: no iOS checkout, skipping port sync check");
}

const filled = fixture.labels.filter(([, k]) => k !== null).length;
console.log(
  failed === 0
    ? `field-matcher: ${cases.length} labels OK (${filled}/${fixture.labels.length} filled on the live Greenhouse form)`
    : `field-matcher: ${failed} failure(s)`
);
process.exit(failed === 0 ? 0 : 1);
