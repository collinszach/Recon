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
    let metro: String?         // target-metro slug, e.g. "nyc"
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
        case id, track, company, title, location, metro, url, status, domain, tier, concerns
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

    enum DueState { case overdue, stale }
    /// What needs attention on this card: a due follow-up or a stale "applied".
    var dueState: DueState? {
        if stage == "closed" { return nil }
        let cal = Calendar.current
        if let s = nextActionDue,
           let d = DateFormatter.ymd.date(from: String(s.prefix(10))),
           cal.startOfDay(for: d) <= cal.startOfDay(for: Date()) { return .overdue }
        if stage == "applied", let s = appliedAt,
           let d = ISO8601DateFormatter().date(from: s),
           let cutoff = cal.date(byAdding: .day, value: -10, to: Date()), d <= cutoff { return .stale }
        return nil
    }
    var dueDateValue: Date? {
        nextActionDue.flatMap { DateFormatter.ymd.date(from: String($0.prefix(10))) }
    }
}

extension DateFormatter {
    static let ymd: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; f.timeZone = .current; return f
    }()
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

struct Contact: Codable, Identifiable, Hashable {
    var id: Int? = nil
    var companyId: Int? = nil
    var company: String? = nil
    var name: String? = nil
    var role: String? = nil
    var email: String? = nil
    var linkedin: String? = nil
    var warmth: String? = nil
    var status: String? = nil          // to_reach | sent | replied | met
    var lastTouch: String? = nil       // yyyy-MM-dd
    var nextTouch: String? = nil
    var lastOutreach: String? = nil
    var notes: String? = nil

    enum CodingKeys: String, CodingKey {
        case id, company, name, role, email, linkedin, warmth, status, notes
        case companyId = "company_id"
        case lastTouch = "last_touch"
        case nextTouch = "next_touch"
        case lastOutreach = "last_outreach"
    }

    static let statuses = ["to_reach", "sent", "replied", "met"]
    var statusLabel: String {
        switch status {
        case "sent": return "Reached out"
        case "replied": return "Replied"
        case "met": return "Met"
        default: return "To reach"
        }
    }
    /// next-touch is due if on/before today
    var nextTouchDue: Bool {
        guard let s = nextTouch, let d = DateFormatter.ymd.date(from: String(s.prefix(10)))
        else { return false }
        return Calendar.current.startOfDay(for: d) <= Calendar.current.startOfDay(for: Date())
    }
}

struct Material: Codable, Identifiable, Hashable {
    var id: Int? = nil
    var roleId: Int? = nil
    var applicationId: Int? = nil
    var kind: String
    var title: String? = nil
    var content: String? = nil
    var createdAt: String? = nil

    enum CodingKeys: String, CodingKey {
        case id, kind, title, content
        case roleId = "role_id"
        case applicationId = "application_id"
        case createdAt = "created_at"
    }
    var kindLabel: String {
        switch kind {
        case "cover_letter": return "Cover letter"
        case "outreach": return "Outreach"
        case "resume": return "Tailored résumé"
        case "prep": return "Interview prep"
        default: return kind.capitalized
        }
    }
}

/// Generic generated document (cover letter, etc.)
struct GenDoc: Codable {
    let title: String?
    let content: String?
    let error: String?
}

/// One person-type worth reaching out to at a target company.
struct ReachTarget: Codable, Identifiable, Hashable {
    var id: String { persona + (opener ?? "") }
    let persona: String
    let warmth: String?
    let why: String?
    let findHint: String?
    let opener: String?
    let linkedinSearch: String?

    enum CodingKeys: String, CodingKey {
        case persona, warmth, why, opener
        case findHint = "find_hint"
        case linkedinSearch = "linkedin_search"
    }
    enum WarmthTone { case warm, medium, cold }
    var warmthTone: WarmthTone {
        switch (warmth ?? "").lowercased() {
        case "warm": return .warm
        case "medium": return .medium
        default: return .cold
        }
    }
}

/// Researched networking plan for a role: who to reach out to and how.
struct NetworkingPlan: Codable {
    let summary: String?
    let targets: [ReachTarget]?
    let error: String?
}

struct Interview: Codable, Identifiable, Hashable {
    var id: Int? = nil
    var applicationId: Int? = nil
    var kind: String? = nil
    var scheduledAt: String? = nil     // yyyy-MM-dd
    var interviewer: String? = nil
    var notes: String? = nil
    var outcome: String? = nil

    enum CodingKeys: String, CodingKey {
        case id, kind, interviewer, notes, outcome
        case applicationId = "application_id"
        case scheduledAt = "scheduled_at"
    }
    static let kinds = ["recruiter", "phone", "technical", "behavioral", "onsite", "final"]
    var dateValue: Date? { scheduledAt.flatMap { DateFormatter.ymd.date(from: String($0.prefix(10))) } }
}

/// Result of POST /api/roles/{id}/interview_prep
struct InterviewPrep: Codable {
    let likely_questions: [String]?
    let talking_points: [String]?
    let questions_to_ask: [String]?
    let watch_outs: [String]?
    let error: String?
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
