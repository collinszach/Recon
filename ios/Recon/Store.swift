import SwiftUI

/// Shared, observable app state. Loads from the API and publishes to the views.
@MainActor
final class Store: ObservableObject {
    @Published var roles: [Role] = []
    @Published var brief: Brief?
    @Published var apps: [AppItem] = []

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
}
