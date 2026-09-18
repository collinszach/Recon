window.ReconAutofill = window.ReconAutofill || {};
window.ReconAutofill.adapters = window.ReconAutofill.adapters || [];

window.ReconAutofill.adapters.push({
  name: "ashby",
  detect() {
    return /jobs\.ashbyhq\.com/.test(location.hostname) ||
      !!document.querySelector("[class*='ashby-application-form']");
  },
  extractFields() {
    return window.ReconAutofill.genericExtract(document);
  },
});

window.ReconAutofill.adapters.push({
  name: "icims",
  detect() {
    return /icims\.com/.test(location.hostname);
  },
  extractFields() {
    const root = document.querySelector("#icims_content_iframe, .iCIMS_JoinOurTeamPortal, form") || document;
    return window.ReconAutofill.genericExtract(root);
  },
});
