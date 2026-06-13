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

    enum CodingKeys: String, CodingKey {
        case id, track, company, title, location, url, status, domain, tier, concerns
        case companyTier = "company_tier"
        case fitScore = "fit_score"
        case whyFit = "why_fit"
        case curriculumHook = "curriculum_hook"
        case tcEstimate = "tc_estimate"
        case isProductPm = "is_product_pm"
    }

    var pay: String { tcEstimate?.isEmpty == false ? tcEstimate! : "Pay not listed" }
    var summary: String { whyFit ?? "Not yet summarized." }
    var fitText: String { fitScore.map { String(format: "%.1f", $0) } ?? "–" }
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

enum Stage: String, CaseIterable, Identifiable {
    case watching, drafting, applied, screen, onsite, offer, closed
    var id: String { rawValue }
    var label: String { rawValue.capitalized }
}
