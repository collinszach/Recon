import Foundation

/// A scored role (internship) from GET /api/roles.
struct Role: Codable, Identifiable, Hashable {
    let id: Int
    let track: String?         // "intern" | "fulltime"
    let company: String?
    let companyId: Int?        // for "never show this employer again"
    let companyTier: String?
    /// Fit tier A/B/C/pass. Scoring was turned off 2026-09-21 (SCORING_ENABLED),
    /// so this is nil on everything ingested since; the old values are still in
    /// the DB. Nothing in the UI reads it any more — kept so decoding a cached
    /// payload written before the switch still works.
    let tier: String?
    let title: String
    let location: String?
    let metro: String?         // target-metro slug, e.g. "nyc" — Zach's 9 curated relocation targets
    let state: String?         // comma-joined US state codes / "remote" / "international" — a multi-
                                // location posting (e.g. "Atlanta, GA; Denver, CO; LA, CA") lists all of them
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
    let description: String?
    let remote: Bool?
    let interest: String?      // "up" | "down" | nil — user feedback
    let isMba: Bool?           // MBA-track internship (rule-based, see api/scan/intern_filter.py)
    let sector: String?        // company sector: big_tech | finance | defense_aerospace | consulting | nil

    enum CodingKeys: String, CodingKey {
        case id, track, company, title, location, metro, state, url, status, domain, tier, concerns, description, remote, interest, sector
        case companyId = "company_id"
        case companyTier = "company_tier"
        case fitScore = "fit_score"
        case whyFit = "why_fit"
        case curriculumHook = "curriculum_hook"
        case tcEstimate = "tc_estimate"
        case isProductPm = "is_product_pm"
        case postedAt = "posted_at"
        case firstSeen = "first_seen"
        case isMba = "is_mba"
    }

    /// Every US state + DC + remote + international — exhaustive by construction
    /// (mirrors api/scan/geo.py STATE_LABELS), so it never misses a location like
    /// the old hand-picked metro list did (2026-08-16: "Denver/CO and other areas").
    static let stateLabels: [(String, String)] = [
        ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"),
        ("CA", "California"), ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"),
        ("FL", "Florida"), ("GA", "Georgia"), ("HI", "Hawaii"), ("ID", "Idaho"),
        ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"), ("KS", "Kansas"),
        ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"),
        ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"), ("MS", "Mississippi"),
        ("MO", "Missouri"), ("MT", "Montana"), ("NE", "Nebraska"), ("NV", "Nevada"),
        ("NH", "New Hampshire"), ("NJ", "New Jersey"), ("NM", "New Mexico"), ("NY", "New York"),
        ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"), ("OK", "Oklahoma"),
        ("OR", "Oregon"), ("PA", "Pennsylvania"), ("RI", "Rhode Island"), ("SC", "South Carolina"),
        ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"), ("UT", "Utah"),
        ("VT", "Vermont"), ("VA", "Virginia"), ("WA", "Washington"), ("WV", "West Virginia"),
        ("WI", "Wisconsin"), ("WY", "Wyoming"), ("DC", "District of Columbia"),
        ("remote", "Remote (US)"), ("international", "International"),
    ]

    static let sectorLabels: [(String, String)] = [
        ("big_tech", "Big Tech"), ("finance", "Finance"),
        ("defense_aerospace", "Defense / Aerospace"), ("consulting", "Consulting"),
    ]
    var sectorLabel: String {
        sector.flatMap { s in Self.sectorLabels.first { $0.0 == s }?.1 } ?? "Other"
    }

    var pay: String { tcEstimate?.isEmpty == false ? tcEstimate! : "Pay not listed" }
    var summary: String { whyFit ?? "Not yet summarized." }
    var fitText: String { fitScore.map { String(format: "%.1f", $0) } ?? "–" }

    /// Every state/remote/international code this role lists (a multi-location
    /// posting spans several). Empty if unparseable.
    var stateCodes: [String] { state?.split(separator: ",").map(String.init) ?? [] }

    /// When Recon first saw it, e.g. "2d ago" — the tracker's primary signal
    /// now that there is no fit score to lead with.
    var firstSeenText: String? {
        guard let d = firstSeenDate else { return nil }
        return Self.ago(d)
    }

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

    static func parseDate(_ s: String?) -> Date? {
        guard let s else { return nil }
        let iso = ISO8601DateFormatter(); iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let iso2 = ISO8601DateFormatter(); iso2.formatOptions = [.withInternetDateTime]
        return iso.date(from: s) ?? iso2.date(from: s)
    }
    var firstSeenDate: Date? { Self.parseDate(firstSeen) }
    /// Ingested after the given baseline → "new since you last looked".
    func isNew(since: Date?) -> Bool {
        guard let since, let d = firstSeenDate else { return false }
        return d > since
    }
    /// First seen today (calendar day, device-local time) — steadier than
    /// isNew(since:), which resets every refresh and can hide roles you
    /// already glanced at earlier today.
    var firstSeenIsToday: Bool {
        guard let d = firstSeenDate else { return false }
        return Calendar.current.isDateInToday(d)
    }
    /// ATS posting opened within the last ~5 days.
    var isFresh: Bool {
        guard let d = Self.parseDate(postedAt) else { return false }
        return Date().timeIntervalSince(d) < 5 * 86400
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
    /// Worth a nudge: a planned follow-up is due, or you reached out and it's
    /// gone quiet (no reply) for ~5+ days.
    var needsFollowUp: Bool {
        if nextTouchDue { return true }
        if status == "sent" {
            guard let s = lastTouch, let d = DateFormatter.ymd.date(from: String(s.prefix(10)))
            else { return true }
            return Date().timeIntervalSince(d) > 5 * 86400
        }
        return false
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

/// A startup Zach is tracking/researching — fintech, defense, sustainability/energy,
/// product-tech-data. Separate from Company, which drives the job-scan pipeline.
struct Startup: Codable, Identifiable, Hashable {
    var id: Int? = nil
    var name: String
    var sector: String? = nil
    var hqLocation: String? = nil
    var stage: String? = nil
    var foundedYear: Int? = nil
    var website: String? = nil
    var oneLiner: String? = nil
    var fundingSummary: String? = nil
    var notes: String? = nil
    var hasWriteup: Bool? = nil
    var writeupGeneratedAt: String? = nil
    var writeupMarkdown: String? = nil
    var createdAt: String? = nil

    enum CodingKeys: String, CodingKey {
        case id, name, sector, stage, website, notes
        case hqLocation = "hq_location"
        case foundedYear = "founded_year"
        case oneLiner = "one_liner"
        case fundingSummary = "funding_summary"
        case hasWriteup = "has_writeup"
        case writeupGeneratedAt = "writeup_generated_at"
        case writeupMarkdown = "writeup_markdown"
        case createdAt = "created_at"
    }

    static let sectors = ["fintech", "defense", "sustainability_energy", "product_tech_data", "other"]
    var sectorLabel: String {
        switch sector {
        case "fintech": return "Fintech"
        case "defense": return "Defense"
        case "sustainability_energy": return "Sustainability / Energy"
        case "product_tech_data": return "Product / Tech / Data"
        default: return "Other"
        }
    }
}

struct StartupContact: Codable, Identifiable, Hashable {
    var id: Int? = nil
    var startupId: Int? = nil
    var name: String? = nil
    var role: String? = nil
    var email: String? = nil
    var linkedin: String? = nil
    var warmth: String? = nil
    var notes: String? = nil

    enum CodingKeys: String, CodingKey {
        case id, name, role, email, linkedin, warmth, notes
        case startupId = "startup_id"
    }
}

// ── Dismissals ──────────────────────────────────────────────
/// A role that was wiped. Compact by design — the server omits the JD text,
/// since this list only ever needs to show what was dismissed and undo it.
struct DismissedRole: Codable, Identifiable, Hashable {
    let id: Int
    let title: String
    let company: String?
    let companyId: Int?
    let location: String?
    let url: String?
    let dismissedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, company, location, url
        case companyId = "company_id"
        case dismissedAt = "dismissed_at"
    }
}

struct DismissedCompany: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let dismissedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, name
        case dismissedAt = "dismissed_at"
    }
}
