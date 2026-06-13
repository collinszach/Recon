import Foundation
import Combine

/// Where the Recon API/dashboard lives. Two presets plus an optional custom
/// override, persisted in UserDefaults so a TestFlight/dev build can be pointed
/// at the home NUC or the public tunnel without rebuilding.
enum Endpoint: String, CaseIterable, Identifiable {
    case auto     // try Local first, fall back to the tunnel
    case tunnel   // public, HTTPS, works anywhere (Cloudflare Tunnel)
    case local    // home / Tailscale, plain HTTP to the NUC
    case custom   // user-entered URL

    var id: String { rawValue }

    var label: String {
        switch self {
        case .auto:   return "Auto (Local → Tunnel)"
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

    /// Per-session memory of whichever candidate base last worked, so Auto mode
    /// doesn't re-probe a dead endpoint on every call.
    var lastWorking: URL?

    private init() {
        let raw = UserDefaults.standard.string(forKey: dEndpoint) ?? Endpoint.auto.rawValue
        endpoint = Endpoint(rawValue: raw) ?? .auto
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

    private var localURLValue: URL  { URL(string: Self.localURL)!  }
    private var tunnelURLValue: URL { URL(string: Self.tunnelURL)! }

    /// Ordered base URLs the API client should try (first that works wins).
    var candidateBaseURLs: [URL] {
        switch endpoint {
        case .auto:   return [localURLValue, tunnelURLValue]
        case .local:  return [localURLValue]
        case .tunnel: return [tunnelURLValue]
        case .custom: return [URL(string: customURL) ?? tunnelURLValue]
        }
    }

    /// The primary base URL (for the WebView / display). In Auto, prefer whatever
    /// last worked, else Local.
    var baseURL: URL {
        if endpoint == .auto { return lastWorking ?? localURLValue }
        return candidateBaseURLs.first ?? tunnelURLValue
    }
}
