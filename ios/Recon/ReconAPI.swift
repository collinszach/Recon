import Foundation

/// Async REST client for the Recon API. Reads the base URL + Access token from
/// AppConfig so it follows the endpoint picker.
struct ReconAPI {
    static let shared = ReconAPI()
    private let config = AppConfig.shared

    enum APIError: LocalizedError {
        case badStatus(Int), decode(String), access
        var errorDescription: String? {
            switch self {
            case .access, .badStatus(403):
                return "Blocked by Cloudflare Access. Open Settings (gear) and add a service token, or switch to the Local endpoint while on Tailscale."
            case .badStatus(let c): return "Server returned HTTP \(c)."
            case .decode(let m): return "Couldn't read the response: \(m)"
            }
        }
    }

    /// True when Access intercepted the request (redirected us to the login page
    /// or returned its HTML challenge instead of our JSON).
    private func isAccessChallenge(_ resp: URLResponse) -> Bool {
        if let host = resp.url?.host, host.contains("cloudflareaccess") { return true }
        if let mime = resp.mimeType, mime.contains("text/html") { return true }
        return false
    }

    /// Join base + path without percent-encoding the query string (which
    /// appendingPathComponent would do to the "?").
    private func makeURL(_ path: String) -> URL {
        let base = config.baseURL.absoluteString.hasSuffix("/")
            ? String(config.baseURL.absoluteString.dropLast())
            : config.baseURL.absoluteString
        return URL(string: base + "/" + path) ?? config.baseURL
    }

    private func get<T: Decodable>(_ path: String, as type: T.Type) async throws -> T {
        var req = URLRequest(url: makeURL(path))
        req.timeoutInterval = 20
        await MainActor.run { config.authorize(&req) }
        let (data, resp) = try await URLSession.shared.data(for: req)
        if isAccessChallenge(resp) { throw APIError.access }
        guard let http = resp as? HTTPURLResponse else { throw APIError.badStatus(-1) }
        guard (200..<300).contains(http.statusCode) else { throw APIError.badStatus(http.statusCode) }
        do { return try JSONDecoder().decode(T.self, from: data) }
        catch { throw APIError.decode(error.localizedDescription) }
    }

    @discardableResult
    private func send<B: Encodable, T: Decodable>(_ method: String, _ path: String,
                                                  body: B, as type: T.Type) async throws -> T {
        var req = URLRequest(url: makeURL(path))
        req.httpMethod = method
        req.timeoutInterval = 20
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(body)
        await MainActor.run { config.authorize(&req) }
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode)
        else { throw APIError.badStatus((resp as? HTTPURLResponse)?.statusCode ?? -1) }
        return try JSONDecoder().decode(T.self, from: data)
    }

    // ---- reads ----
    func roles(minFit: Double = 0) async throws -> [Role] {
        try await get("api/roles?min_fit=\(minFit)", as: [Role].self)
    }
    func brief() async throws -> Brief { try await get("api/brief", as: Brief.self) }
    func applications() async throws -> [AppItem] { try await get("api/applications", as: [AppItem].self) }

    // ---- writes ----
    struct NewApp: Encodable { let role_id: Int; let stage: String }
    func track(roleId: Int, stage: String = "watching") async throws -> AppItem {
        try await send("POST", "api/applications", body: NewApp(role_id: roleId, stage: stage), as: AppItem.self)
    }
    struct StageUpdate: Encodable { let stage: String }
    func move(appId: Int, to stage: String) async throws -> AppItem {
        try await send("PATCH", "api/applications/\(appId)", body: StageUpdate(stage: stage), as: AppItem.self)
    }
}
