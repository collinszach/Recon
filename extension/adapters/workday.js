window.ReconAutofill = window.ReconAutofill || {};
window.ReconAutofill.adapters = window.ReconAutofill.adapters || [];

/**
 * Workday.
 *
 * Workday is not a form with inputs in it — it's a React wizard where most of
 * what looks like a field is something else:
 *   - a "dropdown" is a <button> that opens a listbox in a portal elsewhere in
 *     the DOM, and the value is set by clicking an <li>, not by assignment;
 *   - a date is three separate spin inputs (month / day / year);
 *   - yes/no questions are radio groups whose labels live in sibling nodes;
 *   - the résumé is a file input that only accepts a real File object.
 *
 * So this adapter does its own fill pass (`fill()`) rather than handing a list
 * of elements to the generic filler. The generic path stays as the fallback for
 * plain inputs and for essay questions.
 *
 * Fields are matched on `data-automation-id`, not on label text: Workday's
 * automation ids are stable across tenants, while labels are tenant-authored
 * and translated. Label matching is the second pass.
 *
 * It fills the step you are on and stops. It does not click Next, and it never
 * clicks Submit.
 */
(function (ns) {
  // data-automation-id (or a prefix of one) -> profile key.
  const ID_MAP = [
    [/^legalNameSection_firstName$/i, "first_name"],
    [/^legalNameSection_lastName$/i, "last_name"],
    [/^legalNameSection_middleName$/i, null],
    [/^addressSection_addressLine1$/i, "address_line1"],
    [/^addressSection_addressLine2$/i, null],
    [/^addressSection_city$/i, "city"],
    [/^addressSection_countryRegion$/i, "state"],
    [/^addressSection_postalCode$/i, "zip_code"],
    [/^addressSection_country$/i, "country"],
    [/^country$|^countryDropdown$/i, "country"],
    [/^email$|^emailAddress$/i, "email"],
    [/^phone-?number$|^phoneNumber$/i, "phone"],
    [/^source--dropdown$|^source$/i, "how_heard"],
    [/^linkedinQuestion|linkedin/i, "linkedin_url"],
    [/^websiteQuestion|^website/i, "portfolio_url"],
    [/gender/i, "gender"],
    [/ethnicity|^race/i, "race_ethnicity"],
    [/veteran/i, "veteran_status"],
    [/disability/i, "disability_status"],
  ];

  function profileKeyForId(autoId) {
    for (const [re, key] of ID_MAP) if (re.test(autoId)) return key;
    return null;
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function labelFor(el) {
    return (
      el.getAttribute("aria-label") ||
      ns.extractLabelText(el) ||
      el.getAttribute("data-automation-id") ||
      "field"
    );
  }

  /** Workday's own dropdowns: a button, then a listbox rendered in a portal. */
  async function setDropdown(button, wanted) {
    const target = String(wanted).trim().toLowerCase();
    button.click();
    // The listbox is appended asynchronously, and not inside the button.
    let options = [];
    for (let i = 0; i < 20 && options.length === 0; i++) {
      await sleep(60);
      options = Array.from(
        document.querySelectorAll('[role="option"], [data-automation-id="promptOption"]')
      );
    }
    if (!options.length) return { ok: false, why: "dropdown didn't open" };
    const exact = options.find((o) => o.textContent.trim().toLowerCase() === target);
    const partial = options.find((o) => o.textContent.trim().toLowerCase().includes(target));
    const pick = exact || partial;
    if (!pick) {
      // Close it again so the page isn't left with a stray open menu.
      button.click();
      return { ok: false, why: `no option matching "${wanted}"` };
    }
    pick.click();
    await sleep(80);
    return { ok: true, value: pick.textContent.trim() };
  }

  /** Dates are three spin inputs; fill each with the native setter. */
  async function setDate(container, value) {
    const d = new Date(value);
    if (isNaN(d.getTime())) return { ok: false, why: `unparseable date "${value}"` };
    const parts = {
      month: String(d.getMonth() + 1),
      day: String(d.getDate()),
      year: String(d.getFullYear()),
    };
    let filled = 0;
    for (const [name, v] of Object.entries(parts)) {
      const input = container.querySelector(
        `[data-automation-id="dateSectionMonth-input"], [aria-label*="${name}" i], input[name*="${name}" i]`
      );
      if (!input) continue;
      ns.setNativeValue(input, v);
      filled++;
    }
    return filled ? { ok: true, value } : { ok: false, why: "no date inputs found" };
  }

  /** Yes/no and multiple-choice radio groups. */
  function setRadio(group, wanted) {
    const target = String(wanted).trim().toLowerCase();
    const radios = Array.from(group.querySelectorAll('input[type="radio"], [role="radio"]'));
    for (const r of radios) {
      const text = (labelFor(r) || r.value || "").trim().toLowerCase();
      if (text === target || text.includes(target) ||
          (["true", "yes"].includes(target) && text === "yes") ||
          (["false", "no"].includes(target) && text === "no")) {
        r.click();
        return { ok: true, value: text };
      }
    }
    return { ok: false, why: `no choice matching "${wanted}"` };
  }

  /** Which step of the wizard we're on, for the report header. */
  function currentStep() {
    const el =
      document.querySelector('[data-automation-id="progressBarActiveStep"]') ||
      document.querySelector("h2, h1");
    return (el?.textContent || "").trim().slice(0, 60) || "this step";
  }

  /** Attach the résumé PDF to the file input, if there is one. */
  async function attachResume(getResume) {
    const input = document.querySelector('input[type="file"]');
    if (!input) return null;                       // no upload on this step
    if (input.files && input.files.length) {
      return { label: "Résumé", status: "skipped", detail: "a file is already attached" };
    }
    const file = await getResume();
    if (!file) {
      return { label: "Résumé", status: "attention", detail: "no résumé stored in Recon" };
    }
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    return { label: "Résumé", status: "filled", detail: file.name };
  }

  ns.adapters.push({
    name: "workday",

    detect() {
      return (
        /myworkday\.com|myworkdayjobs\.com/.test(location.hostname) ||
        !!document.querySelector('[data-automation-id="jobPostingHeader"], [data-automation-id]')
      );
    },

    // Kept so the generic pipeline (and essay questions) still work.
    extractFields() {
      const fields = ns.genericExtract(document);
      for (const f of fields) {
        if (f.profileKey) continue;
        const autoId = f.el.getAttribute("data-automation-id") || "";
        if (!autoId) continue;
        const key = profileKeyForId(autoId) ||
          ns.matchProfileKey(autoId.replace(/([a-z])([A-Z])/g, "$1 $2"));
        if (key) {
          f.profileKey = key;
          f.kind = ns.looksLikeEssay(f.label, f.el) ? "essay" : "structured";
        }
      }
      return fields;
    },

    /**
     * Fill the current step. Returns report rows: every field is accounted for
     * as filled / skipped / attention, because a Workday form that looks full
     * and submits empty is the failure mode worth designing against.
     */
    async fill({ profile, getResume }) {
      const report = [];
      const seen = new Set();

      for (const el of document.querySelectorAll("[data-automation-id]")) {
        const autoId = el.getAttribute("data-automation-id") || "";
        const key = profileKeyForId(autoId);
        if (!key || seen.has(el)) continue;
        const value = profile[key];
        const label = labelFor(el);
        // Claim the element before deciding whether we can fill it. This used to
        // sit below the empty-value check, so a field with nothing in the profile
        // was left unclaimed and the label-matching second pass reported it all
        // over again.
        seen.add(el);
        if (value === undefined || value === null || value === "") {
          report.push({ label, status: "attention", detail: `nothing in your profile for ${key}` });
          continue;
        }

        try {
          const tag = el.tagName;
          const role = el.getAttribute("role");
          let res;
          if (tag === "BUTTON" || role === "button" || role === "combobox" ||
              autoId.endsWith("--dropdown")) {
            res = await setDropdown(el, value);
          } else if (el.querySelector('input[type="radio"], [role="radio"]')) {
            res = setRadio(el, value);
          } else if (autoId.toLowerCase().includes("date")) {
            res = await setDate(el, value);
          } else if (tag === "INPUT" || tag === "TEXTAREA") {
            ns.setNativeValue(el, String(value));
            res = { ok: true, value };
          } else {
            continue;    // a wrapper div we have no business writing to
          }
          if (res.ok) {
            ns.highlightField(el);
            report.push({ label, status: "filled", detail: String(res.value ?? value).slice(0, 60) });
          } else {
            report.push({ label, status: "attention", detail: res.why });
          }
        } catch (err) {
          report.push({ label, status: "attention", detail: String(err.message || err) });
        }
      }

      // Plain inputs Workday didn't tag, matched on label text as a second pass.
      for (const f of ns.genericExtract(document)) {
        if (seen.has(f.el) || !f.profileKey || f.kind === "essay") continue;
        const value = profile[f.profileKey];
        if (!value) continue;
        if (ns.fillField(f.el, value)) {
          ns.highlightField(f.el);
          report.push({ label: f.label || f.profileKey, status: "filled",
                        detail: String(value).slice(0, 60) });
        }
      }

      const resume = await attachResume(getResume);
      if (resume) report.push(resume);

      return { step: currentStep(), report };
    },
  });
})(window.ReconAutofill);
