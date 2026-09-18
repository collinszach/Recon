window.ReconAutofill = window.ReconAutofill || {};
window.ReconAutofill.adapters = window.ReconAutofill.adapters || [];

// Always matches — the fallback for any ATS without a dedicated adapter above.
// Registered last so content.js only picks it when nothing more specific detects.
window.ReconAutofill.adapters.push({
  name: "generic",
  detect() {
    return document.querySelectorAll("input, select, textarea").length > 0;
  },
  extractFields() {
    return window.ReconAutofill.genericExtract(document);
  },
});
