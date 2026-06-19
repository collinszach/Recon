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

    /// Join base + path without percent-encoding the query string.
    private func makeURL(_ base: URL, _ path: String) -> URL {
        let b = base.absoluteString.hasSuffix("/") ? String(base.absoluteString.dropLast()) : base.absoluteString
        return URL(string: b + "/" + path) ?? base
    }

    /// Ordered base URLs to try: whatever last worked first (Auto mode), then the
    /// configured candidates.
    @MainActor private func orderedBases() -> [URL] {
        var bases = config.candidateBaseURLs
        if let last = config.lastWorking, let i = bases.firstIndex(of: last) {
            bases.remove(at: i); bases.insert(last, at: 0)
        }
        return bases
    }

    /// Execute a request against each candidate base in order; first success wins
    /// and is remembered for the session. Throws the last error if all fail.
    private func execute(_ method: String, _ path: String, body: Data?) async throws -> Data {
        let bases = await orderedBases()
        var lastError: Error = APIError.badStatus(-1)
        for base in bases {
            var req = URLRequest(url: makeURL(base, path))
            req.httpMethod = method
            req.timeoutInterval = 12
            if let body { req.httpBody = body; req.setValue("application/json", forHTTPHeaderField: "Content-Type") }
            await MainActor.run { config.authorize(&req) }
            do {
                let (data, resp) = try await URLSession.shared.data(for: req)
                if isAccessChallenge(resp) { lastError = APIError.access; continue }
                guard let http = resp as? HTTPURLResponse else { lastError = APIError.badStatus(-1); continue }
                guard (200..<300).contains(http.statusCode) else { lastError = APIError.badStatus(http.statusCode); continue }
                await MainActor.run { config.lastWorking = base }
                return data
            } catch {
                lastError = error   // connection refused / timeout -> try next base
            }
        }
        throw lastError
    }

    private func get<T: Decodable>(_ path: String, as type: T.Type) async throws -> T {
        let data = try await execute("GET", path, body: nil)
        do { return try JSONDecoder().decode(T.self, from: data) }
        catch { throw APIError.decode(error.localizedDescription) }
    }

    @discardableResult
    private func send<B: Encodable, T: Decodable>(_ method: String, _ path: String,
                                                  body: B, as type: T.Type) async throws -> T {
        let data = try await execute(method, path, body: try JSONEncoder().encode(body))
        return try JSONDecoder().decode(T.self, from: data)
    }

    // ---- reads ----
    func roles(minFit: Double = 0) async throws -> [Role] {
        try await get("api/roles?min_fit=\(minFit)", as: [Role].self)
    }
    func brief() async throws -> Brief { try await get("api/brief", as: Brief.self) }
    func applications() async throws -> [AppItem] { try await get("api/applications", as: [AppItem].self) }
    func companies() async throws -> [Company] { try await get("api/companies", as: [Company].self) }
    func contacts() async throws -> [Contact] { try await get("api/contacts", as: [Contact].self) }
    func contacts(company: String) async throws -> [Contact] {
        let q = company.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? company
        return try await get("api/contacts?company=\(q)", as: [Contact].self)
    }
    func addContact(_ c: Contact) async throws -> Contact {
        try await send("POST", "api/contacts", body: c, as: Contact.self)
    }
    func updateContact(_ c: Contact) async throws -> Contact {
        try await send("PATCH", "api/contacts/\(c.id ?? 0)", body: c, as: Contact.self)
    }

    // ---- writes ----
    struct NewApp: Encodable { let role_id: Int; let stage: String }
    func track(roleId: Int, stage: String = "watching") async throws -> AppItem {
        try await send("POST", "api/applications", body: NewApp(role_id: roleId, stage: stage), as: AppItem.self)
    }
    struct StageUpdate: Encodable { let stage: String }
    func move(appId: Int, to stage: String) async throws -> AppItem {
        try await send("PATCH", "api/applications/\(appId)", body: StageUpdate(stage: stage), as: AppItem.self)
    }
    struct AppUpdate: Encodable {
        var stage: String?
        var next_action: String?
        var next_action_due: String?
        var notes: String?
        var outcome: String?
    }
    func updateApp(id: Int, _ body: AppUpdate) async throws -> AppItem {
        try await send("PATCH", "api/applications/\(id)", body: body, as: AppItem.self)
    }

    // ---- resume ----
    func resume() async throws -> ResumeData { try await get("api/resume", as: ResumeData.self) }

    struct OK: Decodable { let status: String? }
    func saveProfile(_ p: ResumeProfile) async throws {
        _ = try await send("PUT", "api/resume", body: p, as: OK.self)
    }
    func addExperience(_ e: Experience) async throws -> Experience {
        try await send("POST", "api/resume/experiences", body: e, as: Experience.self)
    }
    func updateExperience(_ e: Experience) async throws -> Experience {
        try await send("PATCH", "api/resume/experiences/\(e.id ?? 0)", body: e, as: Experience.self)
    }
    func deleteExperience(id: Int) async throws {
        _ = try await execute("DELETE", "api/resume/experiences/\(id)", body: nil)
    }

    func tailor(roleId: Int) async throws -> Tailoring {
        try await send("POST", "api/roles/\(roleId)/tailor", body: [String: String](), as: Tailoring.self)
    }
    func draftOutreach(roleId: Int) async throws -> Outreach {
        try await send("POST", "api/roles/\(roleId)/draft_outreach", body: [String: String](), as: Outreach.self)
    }
    func interviewPrep(roleId: Int) async throws -> InterviewPrep {
        try await send("POST", "api/roles/\(roleId)/interview_prep", body: [String: String](), as: InterviewPrep.self)
    }
    func coverLetter(roleId: Int) async throws -> GenDoc {
        try await send("POST", "api/roles/\(roleId)/cover_letter", body: [String: String](), as: GenDoc.self)
    }
    func networking(roleId: Int) async throws -> NetworkingPlan {
        try await send("POST", "api/roles/\(roleId)/networking", body: [String: String](), as: NetworkingPlan.self)
    }

    // ---- materials vault ----
    func materials(roleId: Int) async throws -> [Material] {
        try await get("api/materials?role_id=\(roleId)", as: [Material].self)
    }
    @discardableResult
    func saveMaterial(_ m: Material) async throws -> Material {
        try await send("POST", "api/materials", body: m, as: Material.self)
    }
    func deleteMaterial(id: Int) async throws {
        _ = try await execute("DELETE", "api/materials/\(id)", body: nil)
    }

    // ---- interviews ----
    func interviews(appId: Int) async throws -> [Interview] {
        try await get("api/applications/\(appId)/interviews", as: [Interview].self)
    }
    func addInterview(appId: Int, _ iv: Interview) async throws -> Interview {
        try await send("POST", "api/applications/\(appId)/interviews", body: iv, as: Interview.self)
    }
    func updateInterview(_ iv: Interview) async throws -> Interview {
        try await send("PATCH", "api/interviews/\(iv.id ?? 0)", body: iv, as: Interview.self)
    }
    func deleteInterview(id: Int) async throws {
        _ = try await execute("DELETE", "api/interviews/\(id)", body: nil)
    }

    struct ChatReq: Encodable { let messages: [[String: String]] }
    func resumeChat(_ turns: [ChatTurn]) async throws -> ChatResponse {
        let msgs = turns.map { ["role": $0.role, "content": $0.content] }
        return try await send("POST", "api/resume/chat", body: ChatReq(messages: msgs), as: ChatResponse.self)
    }
}
