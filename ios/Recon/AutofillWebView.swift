import SwiftUI
import WebKit

/// A WKWebView that can fill the application form it's showing.
///
/// The fill logic is the Chrome extension's, ported: match a field by its
/// label / name / placeholder / autocomplete hint, then write through the
/// **native value setter** and dispatch `input` + `change`. A plain
/// `el.value = x` is discarded on React's next render, which is why a form can
/// look filled and submit empty — the single most important detail here.
///
/// It fills and reports. It never clicks submit.
struct AutofillWebView: UIViewRepresentable {
    let url: URL
    @Binding var isLoading: Bool
    @Binding var loadError: String?
    let reloadToken: Int
    @Binding var fillRequest: Bool
    let profile: [String: String]
    let onReport: (String) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        cfg.defaultWebpagePreferences.allowsContentJavaScript = true
        cfg.websiteDataStore = .default()      // keep the portal's login session
        let web = WKWebView(frame: .zero, configuration: cfg)
        web.navigationDelegate = context.coordinator
        web.allowsBackForwardNavigationGestures = true
        context.coordinator.webView = web
        web.load(URLRequest(url: url))
        return web
    }

    func updateUIView(_ web: WKWebView, context: Context) {
        if fillRequest {
            DispatchQueue.main.async { self.fillRequest = false }
            context.coordinator.fill(profile: profile)
        }
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        private let parent: AutofillWebView
        weak var webView: WKWebView?

        init(_ parent: AutofillWebView) { self.parent = parent }

        func webView(_ w: WKWebView, didStartProvisionalNavigation n: WKNavigation!) {
            parent.isLoading = true
        }
        func webView(_ w: WKWebView, didFinish n: WKNavigation!) {
            parent.isLoading = false
        }
        func webView(_ w: WKWebView, didFail n: WKNavigation!, withError e: Error) {
            parent.isLoading = false
            parent.loadError = e.localizedDescription
        }

        func fill(profile: [String: String]) {
            guard let web = webView,
                  let json = try? JSONSerialization.data(withJSONObject: profile),
                  let profileJSON = String(data: json, encoding: .utf8) else { return }
            web.evaluateJavaScript(Self.script(profileJSON)) { result, error in
                if let error {
                    self.parent.onReport("Couldn't fill: \(error.localizedDescription)")
                } else if let r = result as? [String: Any] {
                    let filled = r["filled"] as? Int ?? 0
                    let seen = r["seen"] as? Int ?? 0
                    let skipped = (r["skipped"] as? [String]) ?? []
                    var msg = "Filled \(filled) of \(seen) fields. Nothing submitted."
                    if !skipped.isEmpty {
                        msg += " Needs you: \(skipped.prefix(4).joined(separator: ", "))"
                    }
                    self.parent.onReport(msg)
                }
            }
        }

        /// Kept deliberately compact and dependency-free — it has to survive
        /// being injected into someone else's page.
        ///
        /// These rules mirror `extension/field-matcher.js`; `extension/tests/
        /// test-field-matcher.js` runs the same fixture against both, because the
        /// first port of this script drifted from the original and that drift is
        /// what broke it. See that file for why the matching is tiered.
        static func script(_ profileJSON: String) -> String {
            """
            (function () {
              const profile = \(profileJSON);
              // [tier, key, patterns] — see extension/field-matcher.js
              const MAP = [
                // Before first_name: "Preferred First Name" contains "First
                // Name", and a legal first name is the wrong thing to put in it.
                ["contact", "preferred_name", [/\\bpreferred\\s*(first\\s*)?name\\b/i, /\\bnickname\\b/i, /\\bgoes\\s*by\\b/i]],
                ["contact", "first_name", [/\\bfirst\\s*name\\b/i, /\\bgiven\\s*name\\b/i]],
                ["contact", "last_name", [/\\blast\\s*name\\b/i, /\\bsurname\\b/i, /\\bfamily\\s*name\\b/i]],
                ["contact", "full_name", [/^name$/i, /\\bfull\\s*name\\b/i, /\\blegal\\s*name\\b/i]],
                ["contact", "email", [/\\be-?mail\\b/i]],
                ["contact", "phone", [/\\bphone\\b/i, /\\bmobile\\b/i, /\\bcell\\b/i]],
                ["contact", "linkedin_url", [/\\blinked ?in\\b/i]],
                ["contact", "github_url", [/\\bgit ?hub\\b/i]],
                ["contact", "portfolio_url", [/\\bportfolio\\b/i, /\\bwebsite\\b/i, /\\bpersonal\\s*site\\b/i]],
                ["field", "address_line1", [/\\bstreet\\b/i, /\\baddress\\s*(line)?\\s*1\\b/i, /^address$/i]],
                ["field", "city", [/\\bcity\\b/i, /^town$/i]],
                ["field", "state", [/\\bstate\\b/i, /\\bprovince\\b/i, /\\bregion\\b/i]],
                ["field", "zip_code", [/\\bzip\\b/i, /\\bpostal\\b/i]],
                ["field", "country", [/\\bcountry\\b/i]],
                ["field", "location", [/^location$/i, /\\bcurrent\\s*location\\b/i]],
                ["field", "headline", [/\\bheadline\\b/i, /\\bcurrent\\s*title\\b/i, /\\bjob\\s*title\\b/i]],
                ["field", "school", [/\\bschool\\b/i, /\\buniversity\\b/i, /\\bcollege\\b/i]],
                ["field", "degree", [/\\bdegree\\b/i]],
                ["field", "discipline", [/\\bdiscipline\\b/i, /\\bmajor\\b/i, /\\bfield\\s*of\\s*study\\b/i]],
                ["question", "pronouns", [/\\bpronoun/i]],
                ["question", "veteran_status", [/\\bveteran\\b/i, /\\bmilitary\\s*status\\b/i]],
                ["question", "disability_status", [/\\bdisabilit/i]],
                ["question", "gender", [/\\bgender\\b/i, /^sex$/i]],
                ["question", "race_ethnicity", [/\\brac(e|ial)\\b/i, /\\bethnic(ity)?\\b/i]],
                ["field", "desired_salary", [/\\bsalary\\b/i, /\\bcompensation\\b/i, /\\bpay\\s*expectation/i]],
                ["field", "earliest_start_date", [/\\bstart\\s*date\\b/i, /\\bavailable\\s*to\\s*start\\b/i, /\\bearliest\\s*start\\b/i]],
                ["field", "notice_period", [/\\bnotice\\s*period\\b/i]],
                ["question", "work_authorized", [/\\bauthoriz(ed|ation)\\s*to\\s*work\\b/i, /\\bwork\\s*authoriz(ation|ed)\\b/i, /\\blegally\\s*authorized\\b/i, /\\bwork\\s*eligib/i]],
                ["question", "requires_sponsorship", [/\\bsponsorship\\b/i, /\\brequire.*visa\\b/i, /\\bneed.*visa\\b/i]],
                ["question", "willing_to_relocate", [/\\brelocat/i]],
                ["question", "how_heard", [/\\bhow\\s*did\\s*you\\s*hear\\b/i, /\\breferral\\b/i, /\\breferred\\s*by\\b/i, /\\bsource\\b/i]]
              ];
              const QUESTION_OPENERS = /^(do|does|did|are|is|was|were|have|has|had|will|would|can|could|should|may|if|what|why|how|when|where|which|who|select|choose|indicate|confirm|specify|please|tell|describe|list|enter|provide)\\b/i;
              // Honeypots. Workday's Create Account step ships an input named
              // "website", 1x1 pixels, labelled "Enter website. This input is for
              // robots only, do not enter if you're human." It is display:block,
              // visibility:visible, opacity:1 with a live offsetParent, so every
              // ordinary hidden-field check misses it — and /\\bwebsite\\b/ matches,
              // so the filler would post a portfolio URL into a bot trap and get
              // the application binned.
              const TRAP_TEXT = /robots?\\s+only|do\\s*not\\s*enter\\s*if\\s*you|leave\\s*(this|it)\\s*(field\\s*)?(empty|blank)|honey\\s*pot|beecatcher/i;
              function looksLikeTrapText(t) { return TRAP_TEXT.test(t || ''); }
              function isHoneypot(el) {
                const idish = [el.name, el.id, el.getAttribute('data-automation-id')]
                  .filter(Boolean).join(' ');
                if (looksLikeTrapText(idish)) return true;
                const r = el.getBoundingClientRect();
                if (r.width <= 2 || r.height <= 2) return true;
                if (r.right < -500 || r.bottom < -500) return true;
                const cs = window.getComputedStyle(el);
                if (cs && (cs.display === 'none' || cs.visibility === 'hidden'
                           || parseFloat(cs.opacity) === 0)) return true;
                return false;
              }
              function isQuestion(t) {
                if (!t) return false;
                if (t.indexOf("?") !== -1) return true;
                const words = t.split(/\\s+/).length;
                if (words > 9) return true;
                // An opener alone isn't enough: "Please confirm your City and
                // State" is a field prompt, while "Select your anticipated
                // bachelor's degree graduation date" (7 words) is a question.
                return words > 6 && QUESTION_OPENERS.test(t);
              }
              // The first *human* label wins. The earlier version concatenated
              // aria-label + name + id + placeholder into one string, which is how
              // an input named "hispanic_ethnicity" matched /city/ — the id soup,
              // not the label, was doing the matching.
              function labelFor(el) {
                if (el.id) {
                  const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                  if (l && l.textContent.trim()) return l.textContent.trim();
                }
                const aria = el.getAttribute('aria-label');
                if (aria && aria.trim()) return aria.trim();
                const by = el.getAttribute('aria-labelledby');
                if (by) {
                  const j = by.split(/\\s+/).map(function (id) {
                    const n = document.getElementById(id); return n ? n.textContent : '';
                  }).join(' ').trim();
                  if (j) return j;
                }
                const wrap = el.closest('label');
                if (wrap && wrap.textContent.trim()) return wrap.textContent.trim();
                let node = el;
                for (let i = 0; i < 4 && node; i++) {
                  node = node.parentElement;
                  if (!node) break;
                  const l = node.querySelector(':scope > label, :scope > .label, :scope > legend');
                  if (l && l.textContent.trim()) return l.textContent.trim();
                }
                return el.getAttribute('placeholder') || '';
              }
              function matchKey(text) {
                if (looksLikeTrapText(text)) return null;
                const q = isQuestion(text);
                for (const entry of MAP) {
                  const tier = entry[0], key = entry[1], pats = entry[2];
                  if (q && tier === "field") continue;
                  for (const re of pats) { if (re.test(text)) return key; }
                }
                return null;
              }
              // A react-select / Downshift combobox: a text input that searches a
              // listbox rendered elsewhere. Writing into it types into the search
              // box without selecting anything, so the field looks filled and
              // submits empty. Modern Greenhouse is built almost entirely from
              // these. Refuse them and say so, rather than claim a fill.
              function isCombobox(el) {
                if (el.tagName !== 'INPUT') return false;
                return el.getAttribute('role') === 'combobox'
                  || el.getAttribute('aria-autocomplete') === 'list'
                  || (el.hasAttribute('aria-controls') && el.hasAttribute('aria-expanded'));
              }
              // React tracks input state through its own value setter, so a
              // plain assignment is reverted on the next render.
              function setValue(el, value) {
                const proto = el.tagName === 'TEXTAREA'
                  ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                if (setter) { setter.call(el, value); } else { el.value = value; }
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
              }
              let filled = 0, seen = 0;
              const skipped = [];
              const fields = document.querySelectorAll(
                'input:not([type=hidden]):not([type=submit]):not([type=button]), textarea, select');
              for (const el of fields) {
                if (el.disabled || el.readOnly) continue;
                const type = (el.type || '').toLowerCase();
                if (type === 'password') continue;              // never touch credentials
                if (type === 'file') continue;                  // résumé is attached elsewhere
                // A checkbox or radio is a decision, not a contact detail. Ticking
                // one on a real application is the user's to make.
                if (type === 'checkbox' || type === 'radio') continue;
                // react-select ships a decoy alongside each combobox: an
                // aria-hidden, tabindex=-1 input carrying `required`, there only
                // to trigger native validation. Filling it *satisfies* that check
                // while nothing is selected — the form then submits with an empty
                // Country and no warning. Strictly worse than leaving it alone.
                if (el.getAttribute('aria-hidden') === 'true') continue;
                if (el.getAttribute('tabindex') === '-1') continue;
                if (isHoneypot(el)) continue;
                const text = labelFor(el).replace(/\\s+/g, ' ').trim();
                if (!text) continue;                            // nothing to match on
                seen++;
                if (el.value) continue;                         // don't overwrite your edits
                const key = matchKey(text);
                const value = key ? profile[key] : null;
                if (value && isCombobox(el)) {
                  const t = text.replace(/\\*+\\s*$/, '').trim().slice(0, 32);
                  if (t && skipped.indexOf(t) === -1) skipped.push(t);
                  continue;
                }
                if (value) {
                  if (el.tagName === 'SELECT') {
                    const want = String(value).toLowerCase();
                    const opt = [...el.options].find(o =>
                      o.text.toLowerCase() === want || o.text.toLowerCase().includes(want));
                    if (opt) {
                      el.value = opt.value;
                      el.dispatchEvent(new Event('change', { bubbles: true }));
                      filled++; el.style.outline = '2px solid #c0522d';
                      continue;
                    }
                  } else {
                    setValue(el, value);
                    filled++; el.style.outline = '2px solid #c0522d';
                    continue;
                  }
                }
                if (el.required || /\\*\\s*$/.test(text)) {
                  const t = text.replace(/\\*+\\s*$/, '').trim().slice(0, 32);
                  if (t && skipped.indexOf(t) === -1) skipped.push(t);
                }
              }
              return { filled: filled, seen: seen, skipped: skipped };
            })();
            """
        }
    }
}
