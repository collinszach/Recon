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
    // Checked before phone and country. Workday's My Information step puts four
    // phone-ish fields in a row — Phone Device Type, Country/Territory Phone
    // Code, Phone Number, Phone Extension — and /\bphone\b/ matched all four,
    // so three of them would have received the phone number. These keys have no
    // profile value on purpose: they claim the label and hand it back to you.
    ["field", "phone_device_type", [/\bphone\s*(device\s*)?type\b/i, /\bdevice\s*type\b/i]],
    ["field", "phone_extension", [/\bphone\s*extension\b/i, /^extension\b/i]],
    ["field", "phone_country_code", [/\b(phone|dialing|dial)\s*code\b/i, /\bcountry\s*code\b/i]],
    // Checked before first_name: "Preferred First Name" contains "First Name",
    // and a legal first name is exactly the wrong thing to put in it.
    ["contact", "preferred_name", [/\bpreferred\s*(first\s*)?name\b/i, /\bnickname\b/i, /\bgoes\s*by\b/i]],
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
    ["field", "discipline", [/\bdiscipline\b/i, /\bmajor\b/i, /\bfield\s*of\s*study\b/i]],
    ["question", "pronouns", [/\bpronoun/i]],
    ["question", "veteran_status", [/\bveteran\b/i, /\bmilitary\s*status\b/i]],
    ["question", "disability_status", [/\bdisabilit/i]],
    ["question", "gender", [/\bgender\b/i, /^sex$/i]],
    ["question", "race_ethnicity", [/\brac(e|ial)\b/i, /\bethnic(ity)?\b/i]],
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

  // Honeypots. Workday ships one on its Create Account step: an input named
  // "website", 1x1 pixels, labelled "Enter website. This input is for robots
  // only, do not enter if you're human." It is display:block, visibility:visible,
  // opacity:1 and has a non-null offsetParent, so every ordinary hidden-field
  // check misses it — and /\bwebsite\b/ matches it, so the filler would post a
  // portfolio URL straight into a bot trap and get the application binned.
  //
  // Split in two so the text half is testable without a DOM.
  const TRAP_TEXT =
    /robots?\s+only|do\s*not\s*enter\s*if\s*you|leave\s*(this|it)\s*(field\s*)?(empty|blank)|honey\s*pot|beecatcher/i;

  ns.looksLikeTrapText = function (text) {
    return TRAP_TEXT.test(text || "");
  };

  ns.isHoneypot = function (el) {
    if (!el) return false;
    if (ns.looksLikeTrapText([el.name, el.id, el.getAttribute("data-automation-id")]
        .filter(Boolean).join(" "))) return true;
    if (typeof el.getBoundingClientRect === "function") {
      const r = el.getBoundingClientRect();
      // A real control is never 1px, and never parked off the left of the world.
      if (r.width <= 2 || r.height <= 2) return true;
      if (r.right < -500 || r.bottom < -500) return true;
    }
    const win = el.ownerDocument && el.ownerDocument.defaultView;
    if (win && typeof win.getComputedStyle === "function") {
      const cs = win.getComputedStyle(el);
      if (cs && (cs.display === "none" || cs.visibility === "hidden" ||
                 parseFloat(cs.opacity) === 0)) return true;
    }
    return false;
  };

  ns.isQuestionLabel = function (labelText) {
    const t = (labelText || "").trim();
    if (!t) return false;
    if (t.includes("?")) return true;
    const words = t.split(/\s+/).length;
    if (words > 9) return true;
    // An opener alone isn't enough: "Please confirm your City and State" is a
    // field prompt, while "Select your anticipated bachelor's degree graduation
    // date" (7 words) is a question. The boundary is empirical — it's set where
    // the surveyed Greenhouse boards put it.
    return words > 6 && QUESTION_OPENERS.test(t);
  };

  ns.matchProfileKey = function (labelText) {
    if (!labelText) return null;
    const t = labelText.trim();
    // Belt and braces: even if the geometry check misses, a label that announces
    // itself as a bot trap never matches a profile key.
    if (ns.looksLikeTrapText(t)) return null;
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

  // A profile holds "CA"; the option reads "California". A naive substring match
  // on "CA" also hits "North Carolina", so the abbreviation is expanded first and
  // matched exactly.
  const US_STATES = {
    AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California",
    CO: "Colorado", CT: "Connecticut", DE: "Delaware", DC: "District of Columbia",
    FL: "Florida", GA: "Georgia", HI: "Hawaii", ID: "Idaho", IL: "Illinois",
    IN: "Indiana", IA: "Iowa", KS: "Kansas", KY: "Kentucky", LA: "Louisiana",
    ME: "Maine", MD: "Maryland", MA: "Massachusetts", MI: "Michigan",
    MN: "Minnesota", MS: "Mississippi", MO: "Missouri", MT: "Montana",
    NE: "Nebraska", NV: "Nevada", NH: "New Hampshire", NJ: "New Jersey",
    NM: "New Mexico", NY: "New York", NC: "North Carolina", ND: "North Dakota",
    OH: "Ohio", OK: "Oklahoma", OR: "Oregon", PA: "Pennsylvania",
    RI: "Rhode Island", SC: "South Carolina", SD: "South Dakota", TN: "Tennessee",
    TX: "Texas", UT: "Utah", VT: "Vermont", VA: "Virginia", WA: "Washington",
    WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming", PR: "Puerto Rico",
  };

  ns.expandAlias = function (key, value) {
    const v = String(value == null ? "" : value).trim();
    if (key === "state" && /^[A-Za-z]{2}$/.test(v)) return US_STATES[v.toUpperCase()] || v;
    return v;
  };

  /// Choose an option by its text, or return -1. Exact match first, then a
  /// prefix match but **only when it is unique** — "United States" picks
  /// "United States of America" because nothing else starts that way.
  ///
  /// There is deliberately no loose substring fallback. On a real application a
  /// confidently wrong answer is worse than a blank one someone has to finish,
  /// and this is the function that would produce it: asked for "Mechanical
  /// Engineering" against a list without it, a substring match returns
  /// "Industrial Mechanical Engineering" and nobody notices.
  ns.pickOption = function (texts, want) {
    const w = String(want == null ? "" : want).trim().toLowerCase();
    if (!w) return -1;
    const norm = (texts || []).map((t) => String(t == null ? "" : t).trim().toLowerCase());
    const exact = norm.indexOf(w);
    if (exact !== -1) return exact;
    const starts = [];
    norm.forEach((t, i) => { if (t && t.startsWith(w)) starts.push(i); });
    return starts.length === 1 ? starts[0] : -1;
  };

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /// Open a combobox and pick an option, verified against Greenhouse 2026-09-22.
  ///
  /// Three things here are not obvious and each one cost a debugging round:
  ///
  ///   1. `el.click()` does nothing. react-select opens on **mousedown**, so the
  ///      full mousedown/mouseup pair has to be dispatched — the same lesson as
  ///      Workday's drill-down chevrons.
  ///   2. mousedown *toggles*. Firing it at an already-open control closes it,
  ///      so the current `aria-expanded` has to be respected.
  ///   3. `[role="option"]` is global and lies. A Greenhouse page with a phone
  ///      widget has 244 options sitting in the DOM before anything is clicked,
  ///      belonging to a different control. Waiting for "options to appear"
  ///      silently reads that other list, so this diffs against a snapshot taken
  ///      before the click and only considers genuinely new nodes.
  ns.selectFromCombobox = async function (el, key, value) {
    const want = ns.expandAlias(key, value);
    if (!want) return { ok: false, why: "nothing in your profile" };
    const mouse = { bubbles: true, cancelable: true, view: window, button: 0 };
    const before = new Set(document.querySelectorAll('[role="option"]'));
    if (el.getAttribute("aria-expanded") !== "true") {
      el.focus();
      el.dispatchEvent(new MouseEvent("mousedown", mouse));
      el.dispatchEvent(new MouseEvent("mouseup", mouse));
    }
    let fresh = [];
    for (let i = 0; i < 20 && fresh.length === 0; i++) {
      await sleep(80);
      fresh = Array.from(document.querySelectorAll('[role="option"]'))
        .filter((o) => !before.has(o));
    }
    if (!fresh.length) return { ok: false, why: "the list didn't open" };
    const idx = ns.pickOption(fresh.map((o) => o.textContent), want);
    if (idx === -1) {
      el.blur();
      return { ok: false, why: `no option matching "${want}"` };
    }
    const chosen = (fresh[idx].textContent || "").trim();
    fresh[idx].dispatchEvent(new MouseEvent("mousedown", mouse));
    fresh[idx].dispatchEvent(new MouseEvent("mouseup", mouse));
    fresh[idx].dispatchEvent(new MouseEvent("click", mouse));
    await sleep(150);
    return { ok: true, value: chosen };
  };

  /// Workday's field identity, normalised across two naming schemes.
  ///
  /// The adapter used to match `data-automation-id` on the element itself,
  /// premised on those ids being "stable across tenants". On GM (surveyed
  /// 2026-09-22, signed in) the inputs carry **no** `data-automation-id` at all:
  /// it sits on a wrapper three levels up, and under a different scheme —
  /// `formField-legalName--firstName`, not `legalNameSection_firstName`. Not one
  /// ID_MAP entry matched, so the adapter's first pass filled nothing there.
  ///
  /// The input's `name` is the clean, stable key (`addressLine1`, `city`,
  /// `postalCode`, `legalName--firstName`). Normalising collapses every spelling
  /// — camelCase, `--`, `_`, the `formField-` prefix — onto plain words.
  ns.normaliseAutomationKey = function (raw) {
    return String(raw == null ? "" : raw)
      .replace(/^formField-/i, "")
      .replace(/[-_]+/g, " ")
      .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
      // and the letter/digit boundary, or "addressLine1" normalises to
      // "address line1" and never matches "address line 1".
      .replace(/([a-zA-Z])([0-9])/g, "$1 $2")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  };

  // Matched against the normalised key. Order matters: "preferred name first
  // name" must be claimed before anything looking for "first name".
  const WORKDAY_KEY_MAP = [
    [/\bpreferred name (first name|given name)\b/, "preferred_name"],
    [/\bmiddle name\b/, null],
    [/\b(legal name )?first name\b|\bgiven name\b/, "first_name"],
    [/\b(legal name )?last name\b|\bfamily name\b/, "last_name"],
    [/\baddress line 2\b/, null],
    [/\baddress line 1\b|^address$/, "address_line1"],
    [/\bcountry region\b|\bregion subdivision\b|^state$/, "state"],
    [/\bpostal code\b|^zip( code)?$/, "zip_code"],
    [/^city$|\baddress city\b/, "city"],
    [/\bcountry phone code\b|\bphone code\b/, "phone_country_code"],
    [/\bphone (device )?type\b/, "phone_device_type"],
    [/\bphone extension\b|^extension$/, "phone_extension"],
    [/\bphone number\b|^phone$/, "phone"],
    [/^country$|\bcountry dropdown\b/, "country"],
    [/^email( address)?$/, "email"],
    [/\bsource\b|\bhow did you hear\b/, "how_heard"],
    [/\blinked ?in\b/, "linkedin_url"],
    [/\bschool\b|\buniversity\b/, "school"],
    [/\bdegree\b/, "degree"],
    [/\bfield of study\b|\bdiscipline\b/, "discipline"],
    [/\bgender\b/, "gender"],
    [/\bethnicity\b|\brace\b|\bhispanic\b/, "race_ethnicity"],
    [/\bveteran\b/, "veteran_status"],
    [/\bdisabilit/, "disability_status"],
  ];

  /// Resolve a profile key from an element's identity candidates.
  ///
  /// `website` is deliberately absent from the map. Workday's honeypot is
  /// `name="website"`, so keying off the name attribute — which is the whole
  /// point of this change — would hand it a portfolio URL and flag the
  /// application as a bot. Trap-shaped candidates are refused outright.
  ns.workdayProfileKey = function (candidates) {
    for (const raw of candidates || []) {
      if (ns.looksLikeTrapText(raw)) return null;
      const k = ns.normaliseAutomationKey(raw);
      if (!k) continue;
      for (const [re, key] of WORKDAY_KEY_MAP) if (re.test(k)) return key;
    }
    return null;
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
    if (ns.isHoneypot(el)) return false;
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
