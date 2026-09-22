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
        static func script(_ profileJSON: String) -> String {
            """
            (function () {
              const profile = \(profileJSON);
              const MAP = [
                ["first_name", /first\\s*name|given\\s*name/i],
                ["last_name", /last\\s*name|surname|family\\s*name/i],
                ["full_name", /^name$|full\\s*name|legal\\s*name/i],
                ["email", /e-?mail/i],
                ["phone", /phone|mobile|cell/i],
                ["linkedin_url", /linked\\s*in/i],
                ["github_url", /git\\s*hub/i],
                ["portfolio_url", /portfolio|website|personal\\s*site/i],
                ["address_line1", /street|address\\s*(line)?\\s*1?/i],
                ["city", /city|town/i],
                ["state", /state|province|region/i],
                ["zip_code", /zip|postal/i],
                ["country", /country/i],
                ["school", /school|university|college/i],
                ["degree", /degree/i],
                ["desired_salary", /salary|compensation|pay\\s*expectation/i],
                ["work_authorized", /authoriz(ed|ation)\\s*to\\s*work|legally\\s*authorized/i],
                ["requires_sponsorship", /sponsorship|require.*visa/i],
                ["how_heard", /how\\s*did\\s*you\\s*hear|referr(al|ed)|source/i]
              ];
              function labelFor(el) {
                const bits = [el.getAttribute('aria-label'), el.name, el.id,
                              el.getAttribute('placeholder'), el.getAttribute('autocomplete')];
                if (el.id) {
                  const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                  if (l) bits.push(l.textContent);
                }
                const wrap = el.closest('label');
                if (wrap) bits.push(wrap.textContent);
                return bits.filter(Boolean).join(' ').slice(0, 300);
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
                if (/password/i.test(el.type || '')) continue;   // never touch credentials
                seen++;
                if (el.value) continue;                          // don't overwrite your edits
                const text = labelFor(el);
                let done = false;
                for (const [key, re] of MAP) {
                  if (!re.test(text)) continue;
                  const value = profile[key];
                  if (!value) break;
                  if (el.tagName === 'SELECT') {
                    const want = String(value).toLowerCase();
                    const opt = [...el.options].find(o =>
                      o.text.toLowerCase() === want || o.text.toLowerCase().includes(want));
                    if (opt) { el.value = opt.value;
                               el.dispatchEvent(new Event('change', { bubbles: true }));
                               done = true; }
                  } else {
                    setValue(el, value);
                    done = true;
                  }
                  break;
                }
                if (done) { filled++; el.style.outline = '2px solid #c0522d'; }
                else if (el.required) {
                  const t = (text || 'a required field').trim().slice(0, 28);
                  if (!skipped.includes(t)) skipped.push(t);
                }
              }
              return { filled: filled, seen: seen, skipped: skipped };
            })();
            """
        }
    }
}
