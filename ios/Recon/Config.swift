import Foundation
import Combine

/// Where the Recon API/dashboard lives. Two presets plus an optional custom
/// override, persisted in UserDefaults so a TestFlight/dev build can be pointed
/// at the home NUC or the public tunnel without rebuilding.
enum Endpoint: String, CaseIterable, Identifiable {
    case tunnel   // public, HTTPS, works anywhere (Cloudflare Tunnel)
    case local    // home / Tailscale, plain HTTP to the NUC
    case custom   // user-entered URL

    var id: String { rawValue }

    var label: String {
        switch self {
        case .tunnel: return "Tunnel (anywhere)"
        case .local:  return "Local (Tailscale)"
        case .custom: return "Custom"
        }
    }
}

final class AppConfig: ObservableObject {
    static let shared = AppConfig()

    // Defaults — adjust the tunnel host if your DNS differs.
    static let tunnelURL = "https://recon.zacharyjcollins.com"
    static let localURL  = "http://100.91.198.28:8010"

    private let dEndpoint = "recon.endpoint"
    private let dCustom   = "recon.customURL"
    private let dCfId     = "recon.cfAccessId"
    private let dCfSecret = "recon.cfAccessSecret"

    @Published var endpoint: Endpoint {
        didSet { UserDefaults.standard.set(endpoint.rawValue, forKey: dEndpoint) }
    }
    @Published var customURL: String {
        didSet { UserDefaults.standard.set(customURL, forKey: dCustom) }
    }
    // Optional Cloudflare Access service token. Needed for native API calls to
    // the tunnel once an Access policy is enforced (the Local/Tailscale endpoint
    // bypasses Access and needs neither).
    @Published var cfAccessId: String {
        didSet { UserDefaults.standard.set(cfAccessId, forKey: dCfId) }
    }
    @Published var cfAccessSecret: String {
        didSet { UserDefaults.standard.set(cfAccessSecret, forKey: dCfSecret) }
    }

    private init() {
        let raw = UserDefaults.standard.string(forKey: dEndpoint) ?? Endpoint.tunnel.rawValue
        endpoint = Endpoint(rawValue: raw) ?? .tunnel
        customURL = UserDefaults.standard.string(forKey: dCustom) ?? Self.localURL
        cfAccessId = UserDefaults.standard.string(forKey: dCfId) ?? ""
        cfAccessSecret = UserDefaults.standard.string(forKey: dCfSecret) ?? ""
    }

    /// Apply Access service-token headers to a request if configured.
    func authorize(_ req: inout URLRequest) {
        if !cfAccessId.isEmpty && !cfAccessSecret.isEmpty {
            req.setValue(cfAccessId, forHTTPHeaderField: "CF-Access-Client-Id")
            req.setValue(cfAccessSecret, forHTTPHeaderField: "CF-Access-Client-Secret")
        }
    }

    /// The base URL the WebView should load.
    var baseURL: URL {
        let s: String
        switch endpoint {
        case .tunnel: s = Self.tunnelURL
        case .local:  s = Self.localURL
        case .custom: s = customURL.isEmpty ? Self.tunnelURL : customURL
        }
        return URL(string: s) ?? URL(string: Self.tunnelURL)!
    }
}
