// Shared across all adapters + content.js. Loaded as a plain script (not a module) via
// chrome.scripting.executeScript's `files` array, so everything hangs off one namespace
// to avoid polluting the page's global scope more than necessary.
window.ReconAutofill = window.ReconAutofill || {};

(function (ns) {
  // profileKey -> [regex patterns matched against label/name/id/placeholder/aria-label text]
  const KEYWORD_MAP = [
    ["first_name", [/first\s*name/i, /given\s*name/i, /^fname$/i]],
    ["last_name", [/last\s*name/i, /surname/i, /family\s*name/i, /^lname$/i]],
    ["full_name", [/^name$/i, /full\s*name/i, /legal\s*name/i]],
    ["email", [/e-?mail/i]],
    ["phone", [/phone/i, /mobile/i, /cell/i]],
    ["linkedin_url", [/linked ?in/i]],
    ["github_url", [/git ?hub/i]],
    ["portfolio_url", [/portfolio/i, /website/i, /personal\s*site/i]],
    ["address_line1", [/street/i, /address\s*(line)?\s*1?/i]],
    ["city", [/city/i, /^town$/i]],
    ["state", [/state/i, /province/i, /region/i]],
    ["zip_code", [/zip/i, /postal/i]],
    ["country", [/country/i]],
    ["location", [/^location$/i, /current\s*location/i]],
    ["headline", [/headline/i, /current\s*title/i, /job\s*title/i]],
    ["work_authorized", [/authoriz(ed|ation)\s*to\s*work/i, /legally\s*authorized/i, /work\s*eligib/i]],
    ["requires_sponsorship", [/sponsorship/i, /require.*visa/i, /need.*visa/i]],
    ["willing_to_relocate", [/relocat/i]],
    ["pronouns", [/pronoun/i]],
    ["veteran_status", [/veteran/i, /military\s*status/i]],
    ["disability_status", [/disability/i]],
    ["gender", [/gender/i, /^sex$/i]],
    ["race_ethnicity", [/race/i, /ethnicity/i]],
    ["desired_salary", [/salary/i, /compensation/i, /pay\s*expectation/i]],
    ["earliest_start_date", [/start\s*date/i, /available\s*to\s*start/i, /earliest\s*start/i]],
    ["notice_period", [/notice\s*period/i]],
    ["how_heard", [/how\s*did\s*you\s*hear/i, /referr(al|ed)/i, /source/i]],
  ];

  // Free-text/essay indicators — if the label matches these, always route to the LLM
  // answer endpoint even if it superficially resembles a structured field.
  const ESSAY_HINTS = [
    /why/i, /tell us/i, /describe/i, /cover\s*letter/i, /additional\s*information/i,
    /anything else/i, /what interests you/i,
  ];

  ns.matchProfileKey = function (labelText) {
    if (!labelText) return null;
    const t = labelText.trim();
    for (const [key, patterns] of KEYWORD_MAP) {
      if (patterns.some((re) => re.test(t))) return key;
    }
    return null;
  };

  ns.looksLikeEssay = function (labelText, el) {
    if (el && el.tagName === "TEXTAREA") return true;
    if (!labelText) return false;
    return ESSAY_HINTS.some((re) => re.test(labelText));
  };

  // Resolve the best human-readable label for a form control.
  ns.extractLabelText = function (el) {
    if (el.id) {
      const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lbl && lbl.textContent.trim()) return lbl.textContent.trim();
    }
    const ariaLabel = el.getAttribute("aria-label");
    if (ariaLabel) return ariaLabel.trim();
    const labelledBy = el.getAttribute("aria-labelledby");
    if (labelledBy) {
      const parts = labelledBy.split(/\s+/).map((id) => document.getElementById(id)?.textContent || "");
      const joined = parts.join(" ").trim();
      if (joined) return joined;
    }
    const closestLabel = el.closest("label");
    if (closestLabel && closestLabel.textContent.trim()) return closestLabel.textContent.trim();
    // Walk up a few ancestors looking for a preceding label-ish node (common in
    // Greenhouse/Lever markup: <div class="field"><label>...</label><input/></div>).
    let node = el;
    for (let i = 0; i < 4 && node; i++) {
      node = node.parentElement;
      if (!node) break;
      const lbl = node.querySelector(":scope > label, :scope > .label, :scope > legend");
      if (lbl && lbl.textContent.trim()) return lbl.textContent.trim();
    }
    return el.getAttribute("placeholder") || el.name || el.id || "";
  };

  // React (and most SPA frameworks) track input state via a custom property setter,
  // so a plain `el.value = x` gets silently overwritten on the next render. This uses
  // the native setter directly, then fires the events React listens for.
  ns.setNativeValue = function (el, value) {
    const proto = el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    const fallback = Object.getOwnPropertyDescriptor(el, "value")?.set;
    if (setter && setter !== fallback) {
      setter.call(el, value);
    } else {
      el.value = value;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  };

  ns.fillField = function (el, value) {
    if (value === null || value === undefined || value === "") return false;
    const tag = el.tagName;
    if (tag === "INPUT" && (el.type === "checkbox" || el.type === "radio")) {
      const want = String(value).toLowerCase();
      const matches = want === "true" || want === "yes" ||
        el.value?.toLowerCase() === want;
      if (el.checked !== matches) {
        el.checked = matches;
        el.dispatchEvent(new Event("click", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      }
      return true;
    }
    if (tag === "SELECT") {
      const want = String(value).toLowerCase();
      const opt = Array.from(el.options).find(
        (o) => o.textContent.trim().toLowerCase().includes(want) ||
          want.includes(o.textContent.trim().toLowerCase())
      );
      if (opt) {
        el.value = opt.value;
        el.dispatchEvent(new Event("change", { bubbles: true }));
        return true;
      }
      return false;
    }
    if (tag === "INPUT" || tag === "TEXTAREA") {
      ns.setNativeValue(el, String(value));
      return true;
    }
    return false;
  };

  ns.highlightField = function (el) {
    el.style.outline = "2px solid #6c5ce7";
    el.style.outlineOffset = "1px";
    el.setAttribute("data-recon-filled", "1");
  };

  function isFillable(el) {
    if (el.disabled || el.readOnly) return false;
    if (el.tagName === "INPUT") {
      const skip = ["hidden", "file", "submit", "button", "reset", "image", "password"];
      return !skip.includes(el.type);
    }
    return el.tagName === "TEXTAREA" || el.tagName === "SELECT";
  }

  // Walk the DOM for form controls and classify each as a structured profile-key
  // match or a free-text/essay question. Shared by every adapter — platform-specific
  // adapters only need to narrow `root` or post-process the result.
  ns.genericExtract = function (root) {
    const els = Array.from((root || document).querySelectorAll("input, select, textarea"))
      .filter(isFillable);
    const seen = new Set();
    const fields = [];
    for (const el of els) {
      if (seen.has(el)) continue;
      seen.add(el);
      const label = ns.extractLabelText(el).replace(/\s+/g, " ").trim();
      if (!label) continue;
      const essay = ns.looksLikeEssay(label, el);
      const profileKey = essay ? null : ns.matchProfileKey(label);
      fields.push({
        el,
        label,
        kind: !essay && profileKey ? "structured" : "essay",
        profileKey,
      });
    }
    return fields;
  };
})(window.ReconAutofill);
