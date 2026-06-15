import Foundation

/// A scored role (internship) from GET /api/roles.
struct Role: Codable, Identifiable, Hashable {
    let id: Int
    let track: String?         // "intern" | "fulltime"
    let company: String?
    let companyTier: String?
    let tier: String?          // fit tier A/B/C/pass
    let title: String
    let location: String?
    let url: String?
    let status: String?
    let fitScore: Double?
    let domain: String?
    let whyFit: String?
    let concerns: String?
    let curriculumHook: String?
    let tcEstimate: String?    // pay / stipend
    let isProductPm: Bool?
    let postedAt: String?
    let firstSeen: String?

    enum CodingKeys: String, CodingKey {
        case id, track, company, title, location, url, status, domain, tier, concerns
        case companyTier = "company_tier"
        case fitScore = "fit_score"
        case whyFit = "why_fit"
        case curriculumHook = "curriculum_hook"
        case tcEstimate = "tc_estimate"
        case isProductPm = "is_product_pm"
        case postedAt = "posted_at"
        case firstSeen = "first_seen"
    }

    var pay: String { tcEstimate?.isEmpty == false ? tcEstimate! : "Pay not listed" }
    var summary: String { whyFit ?? "Not yet summarized." }
    var fitText: String { fitScore.map { String(format: "%.1f", $0) } ?? "–" }

    /// "Posted 3d ago" from the ATS posting date, falling back to when Recon
    /// first saw it ("Seen 2d ago").
    var postedText: String? {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let iso2 = ISO8601DateFormatter(); iso2.formatOptions = [.withInternetDateTime]
        func parse(_ s: String?) -> Date? {
            guard let s else { return nil }
            return iso.date(from: s) ?? iso2.date(from: s)
        }
        if let d = parse(postedAt) { return "Posted \(Self.ago(d))" }
        if let d = parse(firstSeen) { return "Seen \(Self.ago(d))" }
        return nil
    }
    private static func ago(_ d: Date) -> String {
        let days = Int(Date().timeIntervalSince(d) / 86400)
        if days <= 0 { return "today" }
        if days == 1 { return "1d ago" }
        if days < 30 { return "\(days)d ago" }
        let mo = days / 30
        return mo == 1 ? "1mo ago" : "\(mo)mo ago"
    }
}

/// GET /api/brief
struct Brief: Codable {
    let date: String
    let markdown: String
    let newCount: Int?
    let actionCount: Int?
    enum CodingKeys: String, CodingKey {
        case date, markdown
        case newCount = "new_count"
        case actionCount = "action_count"
    }
}

/// GET /api/applications  (a pipeline card)
struct AppItem: Codable, Identifiable, Hashable {
    let id: Int
    let companyName: String?
    let roleTitle: String?
    let roleUrl: String?
    let stage: String
    let outcome: String?
    let appliedAt: String?
    let nextAction: String?
    let nextActionDue: String?
    let notes: String?
    let fitScore: Double?

    enum CodingKeys: String, CodingKey {
        case id, stage, outcome, notes
        case companyName = "company_name"
        case roleTitle = "role_title"
        case roleUrl = "role_url"
        case appliedAt = "applied_at"
        case nextAction = "next_action"
        case nextActionDue = "next_action_due"
        case fitScore = "fit_score"
    }
}

struct Company: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let tier: String?
    let atsName: String?
    let careersUrl: String?
    let notes: String?
    let tracked: Int
    let surfaced: Int

    enum CodingKeys: String, CodingKey {
        case id, name, tier, notes, tracked, surfaced
        case atsName = "ats_name"
        case careersUrl = "careers_url"
    }
    /// Domain + blurb split out of the seed note ("Domain · why ...").
    var domain: String? { notes?.components(separatedBy: " · ").first }
    var blurb: String? {
        guard let n = notes else { return nil }
        let parts = n.components(separatedBy: " · ")
        return parts.count > 1 ? parts.dropFirst().joined(separator: " · ") : n
    }
}

enum Stage: String, CaseIterable, Identifiable {
    case watching, drafting, applied, screen, onsite, offer, closed
    var id: String { rawValue }
    var label: String { rawValue.capitalized }
}

// ── Resume ──────────────────────────────────────────────────
struct ResumeProfile: Codable, Hashable {
    var full_name: String? = nil
    var headline: String? = nil
    var location: String? = nil
    var summary: String? = nil
    var skills: String? = nil
    var education: String? = nil
    var links: String? = nil
}

struct Experience: Codable, Identifiable, Hashable {
    var id: Int? = nil
    var kind: String = "work"
    var company: String? = nil
    var title: String? = nil
    var location: String? = nil
    var start_date: String? = nil
    var end_date: String? = nil
    var bullets: String? = nil
    var sort_order: Int? = nil

    var dateRange: String {
        [start_date, end_date].compactMap { $0 }.joined(separator: " – ")
    }
}

struct ResumeData: Codable {
    var profile: ResumeProfile
    var experiences: [Experience]
}

// ── Résumé coach chat ───────────────────────────────────────
struct ChatTurn: Identifiable, Hashable {
    let id = UUID()
    let role: String       // "user" | "assistant"
    let content: String
}

struct ProposedUpdate: Codable, Hashable {
    let summary: String?
    let profile: ResumeProfile?      // partial profile fields
    let experience: Experience?      // edit (id set) or add (id nil)
}

struct ChatResponse: Codable {
    let reply: String
    let proposed_update: ProposedUpdate?
}

/// Result of POST /api/roles/{id}/draft_outreach
struct Outreach: Codable {
    let subject: String?
    let draft: String?
    let error: String?
}

/// Result of POST /api/roles/{id}/tailor
struct Tailoring: Codable {
    let match_score: Double?
    let verdict: String?
    let strengths: [String]?
    let gaps: [String]?
    let keywords: [String]?
    let tailored_summary: String?
    let suggested_bullets: [String]?
    let error: String?
}
