window.ReconAutofill = window.ReconAutofill || {};
window.ReconAutofill.adapters = window.ReconAutofill.adapters || [];

// Workday is a heavy React app with generated element ids, so aria-label is usually
// the most reliable label source; data-automation-id is a secondary hint when
// aria-label is missing or too generic. Expect this one to need iteration per-tenant.
window.ReconAutofill.adapters.push({
  name: "workday",
  detect() {
    return /myworkday\.com|myworkdayjobs\.com/.test(location.hostname) ||
      !!document.querySelector("[data-automation-id]");
  },
  extractFields() {
    const fields = window.ReconAutofill.genericExtract(document);
    for (const f of fields) {
      if (f.profileKey) continue;
      const autoId = f.el.getAttribute("data-automation-id") || "";
      if (!autoId) continue;
      const guess = window.ReconAutofill.matchProfileKey(autoId.replace(/([a-z])([A-Z])/g, "$1 $2"));
      if (guess) {
        f.profileKey = guess;
        f.kind = window.ReconAutofill.looksLikeEssay(f.label, f.el) ? "essay" : "structured";
      }
    }
    return fields;
  },
});
