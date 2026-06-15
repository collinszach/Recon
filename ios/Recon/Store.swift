import SwiftUI

/// Shared, observable app state. Loads from the API and publishes to the views.
@MainActor
final class Store: ObservableObject {
    @Published var roles: [Role] = []
    @Published var brief: Brief?
    @Published var apps: [AppItem] = []

    @Published var resume: ResumeData?
    @Published var companies: [Company] = []
    @Published var contacts: [Contact] = []

    @Published var loading = false
    @Published var error: String?

    /// Offline support: show last-synced data when the API can't be reached.
    @Published var isOffline = false
    @Published var lastSynced: Date?

    private let api = ReconAPI.shared

    init() {
        // Hydrate from disk so the UI shows instantly, even offline.
        roles = Cache.load([Role].self, "roles") ?? []
        brief = Cache.load(Brief.self, "brief")
        apps = Cache.load([AppItem].self, "apps") ?? []
        companies = Cache.load([Company].self, "companies") ?? []
        contacts = Cache.load([Contact].self, "contacts") ?? []
        resume = Cache.load(ResumeData.self, "resume")
        lastSynced = Cache.load(Date.self, "lastSynced")
    }

    private func markSynced() {
        isOffline = false
        lastSynced = Date()
        Cache.save(lastSynced, "lastSynced")
    }
    /// Show cached data + an offline flag when a load fails but we have a cache.
    private func handleLoadFailure(_ error: Error, hadCache: Bool) {
        if hadCache { isOffline = true }
        else { self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription }
    }

    var lastSyncedText: String? {
        guard let d = lastSynced else { return nil }
        let f = RelativeDateTimeFormatter(); f.unitsStyle = .short
        return f.localizedString(for: d, relativeTo: Date())
    }

    /// Roles worth surfacing: fit-sorted, pass-tier dropped (both tracks).
    var feed: [Role] {
        roles.filter { ($0.tier ?? "pass").uppercased() != "PASS" }
             .sorted { ($0.fitScore ?? 0) > ($1.fitScore ?? 0) }
    }
    var internFeed: [Role]   { feed.filter { ($0.track ?? "intern") == "intern" } }
    var fulltimeFeed: [Role] { feed.filter { $0.track == "fulltime" } }
    var opsFeed: [Role]      { feed.filter { $0.track == "ops" } }
    var passCount: Int { roles.filter { ($0.tier ?? "").uppercased() == "PASS" }.count }

    func refresh() async {
        loading = true; error = nil
        let hadCache = !roles.isEmpty
        do {
            async let r = api.roles()
            async let b = api.brief()
            async let a = api.applications()
            roles = try await r
            brief = try await b
            apps = try await a
            Cache.save(roles, "roles"); Cache.save(brief, "brief"); Cache.save(apps, "apps")
            markSynced()
        } catch {
            handleLoadFailure(error, hadCache: hadCache)
        }
        loading = false
    }

    func track(_ role: Role) async {
        do { let item = try await api.track(roleId: role.id); apps.insert(item, at: 0) }
        catch { self.error = error.localizedDescription }
    }

    func move(_ app: AppItem, to stage: Stage) async {
        do {
            let updated = try await api.move(appId: app.id, to: stage.rawValue)
            if let i = apps.firstIndex(where: { $0.id == app.id }) { apps[i] = updated }
        } catch { self.error = error.localizedDescription }
    }

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
    func tailor(roleId: Int) async -> Tailoring? {
        do { return try await api.tailor(roleId: roleId) }
        catch { self.error = error.localizedDescription; return nil }
    }
    func draftOutreach(roleId: Int) async -> Outreach? {
        do { return try await api.draftOutreach(roleId: roleId) }
        catch { return Outreach(subject: nil, draft: nil,
                                error: (error as? LocalizedError)?.errorDescription ?? error.localizedDescription) }
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
