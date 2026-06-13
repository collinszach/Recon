import SwiftUI
import WebKit

/// Thin WKWebView wrapper with pull-to-refresh, a loading flag, error capture,
/// and external-link handling (mailto:, tel:, and off-site links open in Safari).
struct WebView: UIViewRepresentable {
    let url: URL
    @Binding var isLoading: Bool
    @Binding var loadError: String?
    /// Bumped by the parent to force a reload (e.g. on endpoint change or retry).
    let reloadToken: Int

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        cfg.allowsInlineMediaPlayback = true
        cfg.defaultWebpagePreferences.allowsContentJavaScript = true
        cfg.websiteDataStore = .default()   // persist cookies/Cloudflare Access session

        let web = WKWebView(frame: .zero, configuration: cfg)
        web.navigationDelegate = context.coordinator
        web.uiDelegate = context.coordinator
        web.allowsBackForwardNavigationGestures = true
        web.scrollView.contentInsetAdjustmentBehavior = .automatic
        if #available(iOS 16.4, *) { web.isInspectable = true }

        let refresh = UIRefreshControl()
        refresh.addTarget(context.coordinator,
                          action: #selector(Coordinator.handleRefresh(_:)),
                          for: .valueChanged)
        web.scrollView.refreshControl = refresh
        context.coordinator.webView = web

        web.load(URLRequest(url: url))
        return web
    }

    func updateUIView(_ web: WKWebView, context: Context) {
        // Reload when the token changes or the host URL changes.
        if context.coordinator.lastToken != reloadToken
            || context.coordinator.lastURL != url {
            context.coordinator.lastToken = reloadToken
            context.coordinator.lastURL = url
            web.load(URLRequest(url: url))
        }
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        let parent: WebView
        weak var webView: WKWebView?
        var lastToken: Int = .min
        var lastURL: URL?

        init(_ parent: WebView) {
            self.parent = parent
            self.lastURL = parent.url
            self.lastToken = parent.reloadToken
        }

        @objc func handleRefresh(_ sender: UIRefreshControl) {
            webView?.reload()
        }

        private func setLoading(_ v: Bool) {
            DispatchQueue.main.async { self.parent.isLoading = v }
        }
        private func setError(_ v: String?) {
            DispatchQueue.main.async { self.parent.loadError = v }
        }

        func webView(_ w: WKWebView, didStartProvisionalNavigation n: WKNavigation!) {
            setLoading(true); setError(nil)
        }
        func webView(_ w: WKWebView, didFinish n: WKNavigation!) {
            setLoading(false)
            w.scrollView.refreshControl?.endRefreshing()
        }
        func webView(_ w: WKWebView, didFail n: WKNavigation!, withError e: Error) {
            finishWithError(w, e)
        }
        func webView(_ w: WKWebView, didFailProvisionalNavigation n: WKNavigation!, withError e: Error) {
            finishWithError(w, e)
        }
        private func finishWithError(_ w: WKWebView, _ e: Error) {
            setLoading(false)
            w.scrollView.refreshControl?.endRefreshing()
            let ns = e as NSError
            if ns.code == NSURLErrorCancelled { return }   // user navigated away
            setError(ns.localizedDescription)
        }

        // Open off-site links / mail / tel in the system, keep the app on-site.
        func webView(_ w: WKWebView,
                     decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = action.request.url else { return decisionHandler(.allow) }
            let scheme = url.scheme?.lowercased() ?? ""
            if scheme == "mailto" || scheme == "tel" {
                UIApplication.shared.open(url); return decisionHandler(.cancel)
            }
            // Links the user taps to a different host -> Safari. Same-host stays in app.
            if action.navigationType == .linkActivated,
               let host = url.host, let appHost = parent.url.host, host != appHost {
                UIApplication.shared.open(url); return decisionHandler(.cancel)
            }
            decisionHandler(.allow)
        }

        // target="_blank" popups: load them in the same web view.
        func webView(_ w: WKWebView, createWebViewWith cfg: WKWebViewConfiguration,
                     for action: WKNavigationAction,
                     windowFeatures: WKWindowFeatures) -> WKWebView? {
            if action.targetFrame == nil { w.load(action.request) }
            return nil
        }
    }
}
