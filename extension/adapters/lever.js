window.ReconAutofill = window.ReconAutofill || {};
window.ReconAutofill.adapters = window.ReconAutofill.adapters || [];

window.ReconAutofill.adapters.push({
  name: "lever",
  detect() {
    return !!document.querySelector(".application-form, form[action*='lever']") ||
      /jobs\.lever\.co/.test(location.hostname);
  },
  extractFields() {
    const root = document.querySelector(".application-form") || document;
    const fields = window.ReconAutofill.genericExtract(root);
    // Lever names urls[LinkedIn]/urls[GitHub]/urls[Portfolio] explicitly — trust the
    // name attribute over fuzzy label matching when present.
    for (const f of fields) {
      const name = f.el.getAttribute("name") || "";
      const m = name.match(/urls\[(\w+)\]/i);
      if (m) {
        const kind = m[1].toLowerCase();
        if (kind.includes("linkedin")) { f.kind = "structured"; f.profileKey = "linkedin_url"; }
        else if (kind.includes("github")) { f.kind = "structured"; f.profileKey = "github_url"; }
        else if (kind.includes("portfolio") || kind.includes("website")) {
          f.kind = "structured"; f.profileKey = "portfolio_url";
        }
      }
    }
    return fields;
  },
});
