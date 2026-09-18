import SwiftUI

/// Review — and undo — everything you've rated. Down-voted roles are filtered
/// out of the feed server-side, so without this screen a "not for me" swipe was
/// irreversible and invisible: no record of what you'd passed on, no way to get
/// a role back if you mis-swiped (2026-09-18).
struct RatedRolesView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss
    @State private var rated: [Role] = []
    @State private var loading = true
    @State private var loadError: String?

    private var liked:   [Role] { rated.filter { store.interest(of: $0) == "up" } }
    private var passed:  [Role] { rated.filter { store.interest(of: $0) == "down" } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if loading {
                    ProgressView().tint(Theme.rust).frame(maxWidth: .infinity).padding(.top, 40)
                } else if let loadError {
                    Text(loadError).font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                } else if liked.isEmpty && passed.isEmpty {
                    Text("Nothing rated yet. Swipe some roles and they'll show up here.")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                } else {
                    if !store.pending.isEmpty {
                        Text("\(store.pending.count) rating\(store.pending.count == 1 ? "" : "s") still waiting to sync.")
                            .font(.caption).foregroundStyle(Theme.rust).reconCard(10)
                    }
                    section("Interested", liked, tint: Theme.green)
                    section("Not for me", passed, tint: Theme.rust)
                }
            }
            .padding(16)
        }
        .reconBackground()
        .navigationTitle("Your ratings")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .refreshable { await load() }
    }

    @ViewBuilder
    private func section(_ title: String, _ roles: [Role], tint: Color) -> some View {
        if !roles.isEmpty {
            SectionHeader(title: title, trailing: "\(roles.count)")
            ForEach(roles) { role in
                VStack(alignment: .leading, spacing: 8) {
                    RoleRow(role: role)
                    Button {
                        Task {
                            await store.setInterest(role, nil)
                            await load()
                        }
                    } label: {
                        Label("Undo — put back in the feed", systemImage: "arrow.uturn.backward")
                            .font(.caption.weight(.medium))
                    }
                    .foregroundStyle(tint)
                }
            }
        }
    }

    private func load() async {
        // Start from the local cache, not the server. Ratings made offline live
        // only in Store's optimistic sets + the pending queue until they sync —
        // and those are exactly the ones this screen exists to protect, so it
        // must not depend on the server being reachable to show them.
        var byId: [Int: Role] = [:]
        for r in store.roles { byId[r.id] = r }
        var fetchFailed: String?
        do {
            // include_hidden so "not for me" roles (filtered out of the normal
            // feed server-side) come back too.
            for r in try await ReconAPI.shared.ratedRoles() { byId[r.id] = r }
        } catch {
            fetchFailed = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
        rated = byId.values
            .filter { store.interest(of: $0) != nil }
            .sorted { ($0.fitScore ?? 0) > ($1.fitScore ?? 0) }
        // Only surface the fetch error if we have nothing to show anyway.
        loadError = rated.isEmpty ? fetchFailed : nil
        loading = false
    }
}
