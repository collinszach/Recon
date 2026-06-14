import SwiftUI

/// Shared, observable app state. Loads from the API and publishes to the views.
@MainActor
final class Store: ObservableObject {
    @Published var roles: [Role] = []
    @Published var brief: Brief?
    @Published var apps: [AppItem] = []

    @Published var resume: ResumeData?

    @Published var loading = false
    @Published var error: String?

    private let api = ReconAPI.shared

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
        do {
            async let r = api.roles()
            async let b = api.brief()
            async let a = api.applications()
            roles = try await r
            brief = try await b
            apps = try await a
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
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
        do { resume = try await api.resume() }
        catch { self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription }
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
}
