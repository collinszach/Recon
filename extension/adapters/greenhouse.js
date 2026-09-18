window.ReconAutofill = window.ReconAutofill || {};
window.ReconAutofill.adapters = window.ReconAutofill.adapters || [];

window.ReconAutofill.adapters.push({
  name: "greenhouse",
  detect() {
    return !!document.querySelector("#application_form, .application--form, [action*='greenhouse']") ||
      /boards\.greenhouse\.io|job-boards\.greenhouse\.io/.test(location.hostname);
  },
  extractFields() {
    const root = document.querySelector("#application_form") || document;
    return window.ReconAutofill.genericExtract(root);
  },
});
