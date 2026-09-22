// Shared across all adapters + content.js. Loaded as a plain script (not a module) via
// chrome.scripting.executeScript's `files` array, so everything hangs off one namespace
// to avoid polluting the page's global scope more than necessary.
window.ReconAutofill = window.ReconAutofill || {};

(function (ns) {
  // profileKey -> patterns, matched against the resolved label text.
  //
  // Tiered on purpose. The failure that matters here is not a field left blank —
  // it is a field filled with the wrong thing, on a form the user then submits.
  // A real Rocket Lab Greenhouse posting has 40 labelled controls of which
  // exactly 5 are profile fields; a flat, unanchored map hit three of the other
  // 35, every one of them silently wrong:
  //
  //   "Are you Hispanic/Latino?"                -> city      (ethni-CITY)
  //   "Preferred Internship/Co-Op Start Date"   -> how_heard (P-REFERRED)
  //   "Outside of university coursework, ..."   -> school
  //
  // So: every pattern is word-anchored, and a key only matches a label of the
  // right *shape*.
  //
  //   contact  — unambiguous identity fields; may match any label
  //   field    — short form-field labels ("City", "Degree"); never a question
  //   question — written for question-shaped labels ("Are you authorized to work?")
  const KEYWORD_MAP = [
    ["contact", "first_name", [/\bfirst\s*name\b/i, /\bgiven\s*name\b/i, /^fname$/i]],
    ["contact", "last_name", [/\blast\s*name\b/i, /\bsurname\b/i, /\bfamily\s*name\b/i, /^lname$/i]],
    ["contact", "full_name", [/^name$/i, /\bfull\s*name\b/i, /\blegal\s*name\b/i]],
    ["contact", "email", [/\be-?mail\b/i]],
    ["contact", "phone", [/\bphone\b/i, /\bmobile\b/i, /\bcell\b/i]],
    ["contact", "linkedin_url", [/\blinked ?in\b/i]],
    ["contact", "github_url", [/\bgit ?hub\b/i]],
    ["contact", "portfolio_url", [/\bportfolio\b/i, /\bwebsite\b/i, /\bpersonal\s*site\b/i]],
    ["field", "address_line1", [/\bstreet\b/i, /\baddress\s*(line)?\s*1\b/i, /^address$/i]],
    ["field", "city", [/\bcity\b/i, /^town$/i]],
    ["field", "state", [/\bstate\b/i, /\bprovince\b/i, /\bregion\b/i]],
    ["field", "zip_code", [/\bzip\b/i, /\bpostal\b/i]],
    ["field", "country", [/\bcountry\b/i]],
    ["field", "location", [/^location$/i, /\bcurrent\s*location\b/i]],
    ["field", "headline", [/\bheadline\b/i, /\bcurrent\s*title\b/i, /\bjob\s*title\b/i]],
    ["field", "school", [/\bschool\b/i, /\buniversity\b/i, /\bcollege\b/i]],
    ["field", "degree", [/\bdegree\b/i]],
    ["field", "pronouns", [/\bpronoun/i]],
    ["field", "veteran_status", [/\bveteran\b/i, /\bmilitary\s*status\b/i]],
    ["field", "disability_status", [/\bdisabilit/i]],
    ["field", "gender", [/\bgender\b/i, /^sex$/i]],
    ["field", "race_ethnicity", [/\brace\b/i, /\bethnicity\b/i]],
    ["field", "desired_salary", [/\bsalary\b/i, /\bcompensation\b/i, /\bpay\s*expectation/i]],
    ["field", "earliest_start_date", [/\bstart\s*date\b/i, /\bavailable\s*to\s*start\b/i, /\bearliest\s*start\b/i]],
    ["field", "notice_period", [/\bnotice\s*period\b/i]],
    ["question", "work_authorized", [/\bauthoriz(ed|ation)\s*to\s*work\b/i, /\bwork\s*authoriz(ation|ed)\b/i, /\blegally\s*authorized\b/i, /\bwork\s*eligib/i]],
    ["question", "requires_sponsorship", [/\bsponsorship\b/i, /\brequire.*visa\b/i, /\bneed.*visa\b/i]],
    ["question", "willing_to_relocate", [/\brelocat/i]],
    ["question", "how_heard", [/\bhow\s*did\s*you\s*hear\b/i, /\breferral\b/i, /\breferred\s*by\b/i, /\bsource\b/i]],
  ];

  // Free-text/essay indicators — if the label matches these, always route to the LLM
  // answer endpoint even if it superficially resembles a structured field.
  const ESSAY_HINTS = [
    /why/i, /tell us/i, /describe/i, /cover\s*letter/i, /additional\s*information/i,
    /anything else/i, /what interests you/i,
  ];

  // Labels that read as questions rather than as field names. A question wants a
  // considered answer, not a contact detail pasted into it — so only the keys
  // written for questions are allowed to match one. The word count keeps short
  // imperative field labels ("Enter your city") out of this bucket.
  const QUESTION_OPENERS =
    /^(do|does|did|are|is|was|were|have|has|had|will|would|can|could|should|may|if|what|why|how|when|where|which|who|select|choose|indicate|confirm|specify|please|tell|describe|list|enter|provide)\b/i;

  ns.isQuestionLabel = function (labelText) {
    const t = (labelText || "").trim();
    if (!t) return false;
    if (t.includes("?")) return true;
    const words = t.split(/\s+/).length;
    if (words > 9) return true;
    return words >= 5 && QUESTION_OPENERS.test(t);
  };

  ns.matchProfileKey = function (labelText) {
    if (!labelText) return null;
    const t = labelText.trim();
    const question = ns.isQuestionLabel(t);
    for (const [tier, key, patterns] of KEYWORD_MAP) {
      // Only the "field" tier is shape-restricted. The question-tier patterns
      // ("sponsorship", "authorized to work", "how did you hear") are specific
      // enough to be safe on a short label like "Work authorization" too.
      if (question && tier === "field") continue;
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

  // A react-select / Downshift combobox: a text input that *searches* a listbox
  // rendered elsewhere. Writing into it types into the search box without
  // selecting anything — the control still submits empty while looking filled,
  // which is the exact failure the native-value-setter dance exists to avoid.
  // Modern Greenhouse ("Country", "How did you hear about this opportunity?")
  // is entirely built from these. Until there is a real click-and-pick, we
  // refuse the field and say so rather than claiming a fill we didn't make.
  ns.isCombobox = function (el) {
    if (!el || el.tagName !== "INPUT") return false;
    return el.getAttribute("role") === "combobox" ||
      el.getAttribute("aria-autocomplete") === "list" ||
      el.hasAttribute("aria-controls") && el.hasAttribute("aria-expanded");
  };

  ns.fillField = function (el, value) {
    if (value === null || value === undefined || value === "") return false;
    if (ns.isCombobox(el)) return false;
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
    // react-select ships a decoy alongside each combobox: an aria-hidden,
    // tabindex=-1 input carrying the `required` attribute, there only to trigger
    // native validation. Writing to it is worse than useless — it *satisfies*
    // the browser's required check while nothing is actually selected, so the
    // form submits with an empty Country and no warning.
    if (el.getAttribute("aria-hidden") === "true") return false;
    if (el.getAttribute("tabindex") === "-1") return false;
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
