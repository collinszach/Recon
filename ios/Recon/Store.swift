import SwiftUI

/// Shared, observable app state. Loads from the API and publishes to the views.
@MainActor
final class Store: ObservableObject {
    @Published var roles: [Role] = []
    @Published var brief: Brief?
    @Published var apps: [AppItem] = []

    @Published var resume: ResumeData?
    /// Boards connected in the last week, with how much back catalogue each
    /// brought — so a 396-role batch is explained rather than unexplained.
    @Published var recentBoards: [ConnectedBoard] = []
    /// Replies Recon found, each waiting on a yes/no. Nothing moves until one
    /// is accepted.
    @Published var mailProposals: [MailProposal] = []
    /// Flat contact/EEO profile used to fill application forms in-app. Same
    /// payload the Chrome extension uses, so the two can't drift.
    @Published var autofillProfile: [String: String] = [:]
    @Published var resumeOnFile = false

    /// Enough of a profile to be worth pressing Fill.
    var autofillReady: Bool {
        ["first_name", "last_name", "email"].allSatisfy {
            !(autofillProfile[$0] ?? "").isEmpty
        }
    }
    @Published var companies: [Company] = []
    @Published var contacts: [Contact] = []

    @Published var loading = false
    @Published var error: String?

    /// Offline support: show last-synced data when the API can't be reached.
    @Published var isOffline = false
    @Published var lastSynced: Date?

    /// Optimistic feedback overrides (bridge UI until the next server refresh).
    @Published var hiddenRoleIds: Set<Int> = []
    @Published var likedRoleIds: Set<Int> = []
    /// Employers wiped with "never show this again". Persisted for the same
    /// reason the role sets are: the server knows, but the app must still be
    /// right about it offline and immediately after a relaunch.
    @Published var dismissedCompanyIds: Set<Int> = []

    /// Ratings/tracks that couldn't reach the server, persisted to disk and
    /// replayed on the next successful refresh.
    @Published private(set) var pending: [PendingAction] = []

    /// Baseline for "new since you last looked": the sync time *before* this one.
    /// Roles first seen after it are flagged NEW until the next refresh advances it.
    @Published var newSince: Date?

    private let api = ReconAPI.shared

    init() {
        // Hydrate from disk so the UI shows instantly, even offline.
        roles = Cache.load([Role].self, "roles") ?? []
        brief = Cache.load(Brief.self, "brief")
        apps = Cache.load([AppItem].self, "apps") ?? []
        companies = Cache.load([Company].self, "companies") ?? []
        contacts = Cache.load([Contact].self, "contacts") ?? []
        recentBoards = Cache.load([ConnectedBoard].self, "recentBoards") ?? []
        mailProposals = Cache.load([MailProposal].self, "mailProposals") ?? []
        autofillProfile = Cache.load([String: String].self, "autofillProfile") ?? [:]
        resume = Cache.load(ResumeData.self, "resume")
        lastSynced = Cache.load(Date.self, "lastSynced")
        newSince = Cache.load(Date.self, "newSince")
        pending = Cache.load([PendingAction].self, "pending") ?? []
        // Re-apply queued ratings so the feed looks the same after a restart as
        // it did when they were made — otherwise a role you already passed on
        // reappears until the queue drains.
        for a in pending where a.kind == .interest {
            if a.value == "up" { likedRoleIds.insert(a.roleId) }
            if a.value == "down" { hiddenRoleIds.insert(a.roleId) }
        }
        for a in pending where a.kind == .dismissRole { hiddenRoleIds.insert(a.roleId) }
        // The queue only holds ratings that *failed* to send, so it can't be the
        // whole picture — a rating the server accepted leaves no trace in it.
        // Persist the sets themselves too, so the feed after a relaunch matches
        // the feed you left, whether or not the server was reachable.
        hiddenRoleIds.formUnion(Cache.load(Set<Int>.self, "hiddenRoleIds") ?? [])
        likedRoleIds.formUnion(Cache.load(Set<Int>.self, "likedRoleIds") ?? [])
        dismissedCompanyIds.formUnion(Cache.load(Set<Int>.self, "dismissedCompanyIds") ?? [])
        for a in pending where a.kind == .dismissCompany {
            dismissedCompanyIds.insert(a.roleId)   // carries the company id
        }
    }

    private func saveRatingSets() {
        Cache.save(hiddenRoleIds, "hiddenRoleIds")
        Cache.save(likedRoleIds, "likedRoleIds")
        Cache.save(dismissedCompanyIds, "dismissedCompanyIds")
    }

    private func markSynced() {
        isOffline = false
        lastSynced = Date()
        Cache.save(lastSynced, "lastSynced")
    }
    /// Show cached data + an offline flag when a load fails but we have a cache.
    /// The specific error (e.g. Cloudflare Access rejecting a bad service token)
    /// is captured either way — it used to be dropped whenever hadCache was true,
    /// which is the common case, so the banner always showed a generic Tailscale
    /// message even when the real cause was something else entirely.
    private func handleLoadFailure(_ error: Error, hadCache: Bool) {
        self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        if hadCache { isOffline = true }
    }

    /// "just now" / "4m ago" — bare, so callers can phrase it ("synced …",
    /// "Showing data from …"). RelativeDateTimeFormatter renders a
    /// just-finished sync as "in 0 sec.", which reads as a bug.
    var lastSyncedText: String? {
        guard let d = lastSynced else { return nil }
        let age = Date().timeIntervalSince(d)
        if age < 60 { return "just now" }
        let f = RelativeDateTimeFormatter(); f.unitsStyle = .short
        return f.localizedString(for: d, relativeTo: Date())
    }

    func isNew(_ role: Role) -> Bool { role.isNew(since: newSince) }
    /// Count of feed roles first seen since the last refresh.
    var newCount: Int { feed.filter { $0.isNew(since: newSince) }.count }
    /// Count of feed roles first seen today (calendar day) — what drives the
    /// "New" badge and today's summary, since it's stable across refreshes.
    var todayCount: Int { feed.filter { $0.firstSeenIsToday }.count }
    /// Roles worth rating: in the current feed, not yet swiped on.
    func unratedDeck(from roles: [Role]) -> [Role] {
        roles.filter { interest(of: $0) == nil }
    }

    /// The tracker feed: everything the server sent, newest first, minus what
    /// has been wiped. The server already decides relevance (it only returns
    /// in-track roles) and already drops dismissals — this second pass exists so
    /// a wipe takes effect instantly and survives offline, before any refresh.
    ///
    /// Dismissals go through `interest(of:)`, which reads the *server-recorded*
    /// interest as well as the optimistic sets. Filtering on `hiddenRoleIds`
    /// alone only covered the in-memory set, which is rebuilt at launch from the
    /// offline queue — and that queue by definition holds only the wipes that
    /// never reached the server. Every wipe that succeeded was forgotten on
    /// relaunch, so roles already passed on came back; offline, for good.
    var feed: [Role] {
        roles.filter { interest(of: $0) != "down" && !dismissedCompanyIds.contains($0.companyId ?? -1) }
             .sorted { ($0.effectiveDate ?? .distantPast) > ($1.effectiveDate ?? .distantPast) }
    }

    /// What the employer posted today. Strictly `posted_at` — an undated role
    /// is not today's news, which is the whole point: of 80 roles that arrived
    /// on 2026-09-21, 7 were posted that day and 68 were a newly connected
    /// board's back catalogue (see Role.isBackfill).
    var postedToday: [Role] {
        feed.filter { $0.postedToday && $0.isBackfill != true }
    }

    /// Posted in the last week, today excluded — the "earlier this week" list.
    var postedThisWeek: [Role] {
        let cutoff = Date().addingTimeInterval(-7 * 86_400)
        return feed.filter {
            guard let d = $0.postedDate, $0.isBackfill != true else { return false }
            return d >= cutoff && !Calendar.current.isDateInToday(d)
        }
    }

    /// Boards that publish no posting date still tell us something: a posting
    /// that wasn't on the board yesterday and is there today is new, and the
    /// scan already knows which rows it just created. So "newly listed" is a
    /// real signal, not a fallback — as long as the board isn't being read for
    /// the first time, where everything is new by definition (isBackfill).
    var newlyListedToday: [Role] {
        feed.filter { !$0.postedIsKnown && $0.isBackfill != true && $0.firstSeenIsToday }
    }

    /// Everything genuinely new today: posted today where the board says so,
    /// plus first appearances on boards that don't date their postings.
    var newToday: [Role] {
        (postedToday + newlyListedToday)
            .sorted { ($0.effectiveDate ?? .distantPast) > ($1.effectiveDate ?? .distantPast) }
    }

    /// Same, over the last week — what the browse tab's "New" segment shows.
    func newWithin(days: Int) -> [Role] {
        let cutoff = Date().addingTimeInterval(-Double(days) * 86_400)
        return feed.filter { r in
            guard r.isBackfill != true else { return false }
            if let p = r.postedDate { return p >= cutoff }
            return (r.firstSeenDate ?? .distantPast) >= cutoff
        }
    }

    /// Recently arrived with no posting date and not today — still worth a
    /// group of its own, since their real age is unknown.
    var undatedArrivals: [Role] {
        let cutoff = Date().addingTimeInterval(-7 * 86_400)
        return feed.filter {
            !$0.postedIsKnown && $0.isBackfill != true && !$0.firstSeenIsToday
                && ($0.firstSeenDate ?? .distantPast) >= cutoff
        }
    }

    /// Effective interest for a role, honoring optimistic overrides.
    func interest(of role: Role) -> String? {
        if likedRoleIds.contains(role.id) { return "up" }
        if hiddenRoleIds.contains(role.id) { return "down" }
        return role.interest
    }

    /// Record 👍/👎 (or clear). Down-voted roles drop out of the feed at once.
    /// If the server can't be reached the action is queued to disk and replayed
    /// on the next successful refresh — swiping offline used to update the UI
    /// optimistically and then silently lose the rating on the next launch,
    /// since the optimistic sets live only in memory (2026-09-18: an entire
    /// session's worth of ratings was lost this way).
    func setInterest(_ role: Role, _ value: String?) async {
        likedRoleIds.remove(role.id); hiddenRoleIds.remove(role.id)
        if value == "up" { likedRoleIds.insert(role.id) }
        if value == "down" { hiddenRoleIds.insert(role.id) }
        saveRatingSets()
        do { try await api.feedback(roleId: role.id, value: value) }
        catch { enqueue(.init(roleId: role.id, kind: .interest, value: value)) }
    }

    /// Wipe a role: gone from the feed now, gone after a relaunch, gone after
    /// the next scan re-ingests the same posting.
    func dismiss(_ role: Role) async {
        likedRoleIds.remove(role.id)
        hiddenRoleIds.insert(role.id)
        saveRatingSets()
        do { try await api.dismiss(roleId: role.id) }
        catch { enqueue(.init(roleId: role.id, kind: .dismissRole)) }
    }

    func undismiss(_ roleId: Int) async {
        hiddenRoleIds.remove(roleId)
        saveRatingSets()
        do { try await api.undismiss(roleId: roleId) }
        catch { self.error = error.localizedDescription }
    }

    /// Never show this employer again. Returns how many roles it took out of
    /// the feed so the caller can say so instead of the list just shrinking.
    @discardableResult
    func dismissCompany(_ companyId: Int) async -> Int {
        dismissedCompanyIds.insert(companyId)
        saveRatingSets()
        let hidden = roles.filter { $0.companyId == companyId }.count
        do { _ = try await api.dismiss(companyId: companyId) }
        catch { enqueue(.init(roleId: companyId, kind: .dismissCompany)) }
        return hidden
    }

    func undismissCompany(_ companyId: Int) async {
        dismissedCompanyIds.remove(companyId)
        saveRatingSets()
        do { try await api.undismiss(companyId: companyId) }
        catch { self.error = error.localizedDescription }
    }

    // ── offline queue ────────────────────────────────────────────────────
    /// A rating/track that never reached the server, kept so it isn't lost.
    struct PendingAction: Codable, Equatable {
        /// `dismissRole` / `dismissCompany` are wipes; for dismissCompany the
        /// `roleId` field carries the *company* id (the queue is keyed by
        /// (id, kind), so the two never collide).
        enum Kind: String, Codable { case interest, track, dismissRole, dismissCompany }
        let roleId: Int
        let kind: Kind
        var value: String? = nil     // "up" / "down" / nil — interest only
    }

    private func enqueue(_ a: PendingAction) {
        pending.removeAll { $0.roleId == a.roleId && $0.kind == a.kind }
        pending.append(a)
        Cache.save(pending, "pending")
        error = "Saved offline — \(pending.count) change\(pending.count == 1 ? "" : "s") will sync when Recon is reachable."
    }

    /// Replay queued actions. Anything that still fails stays queued.
    private func flushPending() async {
        guard !pending.isEmpty else { return }
        var stillFailing: [PendingAction] = []
        for a in pending {
            do {
                switch a.kind {
                case .interest: try await api.feedback(roleId: a.roleId, value: a.value)
                case .track:    _ = try await api.track(roleId: a.roleId)
                case .dismissRole:    try await api.dismiss(roleId: a.roleId)
                case .dismissCompany: _ = try await api.dismiss(companyId: a.roleId)
                }
            } catch {
                stillFailing.append(a)
            }
        }
        pending = stillFailing
        Cache.save(pending, "pending")
    }
    /// The server sends only in-track roles (TRACK_MODE=intern → internships),
    /// so these are just lenses on the same feed, kept for the views that read
    /// them by name.
    var internFeed: [Role]   { feed.filter { ($0.track ?? "intern") == "intern" } }
    var fulltimeFeed: [Role] { feed.filter { $0.track == "fulltime" } }
    var opsFeed: [Role]      { feed.filter { $0.track == "ops" } }
    var dismissedCount: Int { hiddenRoleIds.count }

    func refresh() async {
        loading = true; error = nil
        let hadCache = !roles.isEmpty
        let prevSync = lastSynced     // baseline for "new since you last looked"
        do {
            async let r = api.roles()
            async let b = api.brief()
            async let a = api.applications()
            roles = try await r
            brief = try await b
            apps = try await a
            // Non-fatal: an older server without /api/boards/recent just means
            // no "connected" lines, not a failed refresh.
            recentBoards = (try? await api.recentBoards()) ?? recentBoards
            Cache.save(recentBoards, "recentBoards")
            mailProposals = (try? await api.mailProposals()) ?? mailProposals
            Cache.save(mailProposals, "mailProposals")
            autofillProfile = (try? await api.autofillProfile()) ?? autofillProfile
            Cache.save(autofillProfile, "autofillProfile")
            resumeOnFile = (try? await api.resumeOnFile()) ?? resumeOnFile
            Cache.save(roles, "roles"); Cache.save(brief, "brief"); Cache.save(apps, "apps")
            markSynced()
            newSince = prevSync; Cache.save(newSince, "newSince")
            // Server is reachable again — replay anything queued while offline.
            await flushPending()
        } catch {
            handleLoadFailure(error, hadCache: hadCache)
        }
        loading = false
    }

    func track(_ role: Role, stage: String = "watching") async {
        do { let item = try await api.track(roleId: role.id, stage: stage); apps.insert(item, at: 0) }
        catch { enqueue(.init(roleId: role.id, kind: .track)) }
    }

    /// Accept a mail proposal: the application moves, the event is logged
    /// server-side, and the pipeline is refetched so the change is visible.
    func acceptProposal(_ p: MailProposal, stage: String? = nil) async {
        mailProposals.removeAll { $0.id == p.id }
        Cache.save(mailProposals, "mailProposals")
        do {
            try await api.acceptProposal(id: p.id, stage: stage)
            apps = (try? await api.applications()) ?? apps
            Cache.save(apps, "apps")
        } catch { self.error = error.localizedDescription }
    }

    func dismissProposal(_ p: MailProposal) async {
        mailProposals.removeAll { $0.id == p.id }
        Cache.save(mailProposals, "mailProposals")
        do { try await api.dismissProposal(id: p.id) }
        catch { self.error = error.localizedDescription }
    }

    func move(_ app: AppItem, to stage: Stage) async {
        do {
            let updated = try await api.move(appId: app.id, to: stage.rawValue)
            if let i = apps.firstIndex(where: { $0.id == app.id }) { apps[i] = updated }
            Cache.save(apps, "apps")
        } catch { self.error = error.localizedDescription }
    }
    func updateApp(_ app: AppItem, _ body: ReconAPI.AppUpdate) async {
        do {
            let updated = try await api.updateApp(id: app.id, body)
            if let i = apps.firstIndex(where: { $0.id == app.id }) { apps[i] = updated }
            Cache.save(apps, "apps")
        } catch { self.error = error.localizedDescription }
    }

    /// Client-side funnel (works offline).
    var stageCounts: [String: Int] {
        Dictionary(grouping: apps, by: { $0.stage }).mapValues(\.count)
    }
    var needActionCount: Int { apps.filter { $0.dueState != nil }.count }

    /// Contacts worth nudging: next touch due or reached out with no reply for 5+ days.
    var followUpContacts: [Contact] { contacts.filter { $0.needsFollowUp } }
    /// Total items needing attention across pipeline apps and networking contacts.
    var totalNudgeCount: Int { needActionCount + followUpContacts.count }

    // ---- resume ----
    func loadResume() async {
        do { resume = try await api.resume(); Cache.save(resume, "resume") }
        catch { handleLoadFailure(error, hadCache: resume != nil) }
    }
    func loadCompanies() async {
        do { companies = try await api.companies(); Cache.save(companies, "companies") }
        catch { handleLoadFailure(error, hadCache: !companies.isEmpty) }
    }
    func loadContacts() async {
        do { contacts = try await api.contacts(); Cache.save(contacts, "contacts") }
        catch { handleLoadFailure(error, hadCache: !contacts.isEmpty) }
    }
    func saveContact(_ c: Contact) async {
        do {
            let saved = c.id == nil ? try await api.addContact(c) : try await api.updateContact(c)
            if let i = contacts.firstIndex(where: { $0.id == saved.id }) { contacts[i] = saved }
            else { contacts.insert(saved, at: 0) }
            Cache.save(contacts, "contacts")
        } catch { self.error = error.localizedDescription }
    }
    func saveProfile(_ p: ResumeProfile) async {
        do { try await api.saveProfile(p); resume?.profile = p }
        catch { self.error = error.localizedDescription }
    }
    func saveExperience(_ e: Experience) async {
        do {
            let saved = e.id == nil ? try await api.addExperience(e) : try await api.updateExperience(e)
            if let i = resume?.experiences.firstIndex(where: { $0.id == saved.id }) {
                resume?.experiences[i] = saved
            } else {
                resume?.experiences.append(saved)
                resume?.experiences.sort { ($0.sort_order ?? 0) < ($1.sort_order ?? 0) }
            }
        } catch { self.error = error.localizedDescription }
    }
    func deleteExperience(_ e: Experience) async {
        guard let id = e.id else { return }
        do { try await api.deleteExperience(id: id); resume?.experiences.removeAll { $0.id == id } }
        catch { self.error = error.localizedDescription }
    }
    // ── LLM result caches (session-scoped; cleared on app restart) ──────────
    private var tailorCache:    [Int: Tailoring]       = [:]
    private var outreachCache:  [Int: Outreach]        = [:]
    private var prepCache:      [Int: InterviewPrep]   = [:]
    private var networkCache:   [Int: NetworkingPlan]  = [:]
    private var coverCache:     [Int: GenDoc]          = [:]

    func tailor(roleId: Int) async -> Tailoring? {
        if let hit = tailorCache[roleId] { return hit }
        do { let r = try await api.tailor(roleId: roleId); tailorCache[roleId] = r; return r }
        catch { self.error = error.localizedDescription; return nil }
    }
    func draftOutreach(roleId: Int) async -> Outreach? {
        if let hit = outreachCache[roleId] { return hit }
        do { let r = try await api.draftOutreach(roleId: roleId); outreachCache[roleId] = r; return r }
        catch { return Outreach(subject: nil, draft: nil,
                                error: (error as? LocalizedError)?.errorDescription ?? error.localizedDescription) }
    }
    func interviewPrep(roleId: Int) async -> InterviewPrep? {
        if let hit = prepCache[roleId] { return hit }
        do { let r = try await api.interviewPrep(roleId: roleId); prepCache[roleId] = r; return r }
        catch { return InterviewPrep(likely_questions: nil, talking_points: nil, questions_to_ask: nil,
                                     watch_outs: nil,
                                     error: (error as? LocalizedError)?.errorDescription ?? error.localizedDescription) }
    }
    func networking(roleId: Int) async -> NetworkingPlan {
        if let hit = networkCache[roleId] { return hit }
        do { let r = try await api.networking(roleId: roleId); networkCache[roleId] = r; return r }
        catch { return NetworkingPlan(summary: nil, targets: nil,
                                      error: (error as? LocalizedError)?.errorDescription ?? error.localizedDescription) }
    }
    func coverLetter(roleId: Int) async -> GenDoc? {
        if let hit = coverCache[roleId] { return hit }
        do { let r = try await api.coverLetter(roleId: roleId); coverCache[roleId] = r; return r }
        catch { return GenDoc(title: nil, content: nil,
                              error: (error as? LocalizedError)?.errorDescription ?? error.localizedDescription) }
    }
    @discardableResult
    func saveMaterial(_ m: Material) async -> Bool {
        do { try await api.saveMaterial(m); return true }
        catch { self.error = error.localizedDescription; return false }
    }
    func resumeChat(_ turns: [ChatTurn]) async -> ChatResponse? {
        do { return try await api.resumeChat(turns) }
        catch { self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription; return nil }
    }
    /// Apply a coach-proposed update via the existing CRUD, then refresh.
    func applyProposed(_ up: ProposedUpdate) async {
        if let p = up.profile { await saveProfile(mergedProfile(p)) }
        if let e = up.experience { await saveExperience(e) }
        await loadResume()
    }
    /// Merge a partial profile from the coach onto the current one (don't blank fields).
    private func mergedProfile(_ p: ResumeProfile) -> ResumeProfile {
        var base = resume?.profile ?? ResumeProfile()
        if let v = p.full_name { base.full_name = v }
        if let v = p.headline { base.headline = v }
        if let v = p.location { base.location = v }
        if let v = p.summary { base.summary = v }
        if let v = p.skills { base.skills = v }
        if let v = p.education { base.education = v }
        if let v = p.links { base.links = v }
        return base
    }
}
