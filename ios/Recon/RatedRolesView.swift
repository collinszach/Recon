import SwiftUI

/// Review — and undo — everything you've wiped: roles and whole employers.
/// Dismissed roles are filtered out of the feed server-side, so without this
/// screen a wipe is irreversible and invisible: no record of what you passed
/// on, no way back from a mis-swipe (2026-09-18).
///
/// Reads the local cache first and only then the server. A wipe made offline
/// lives in Store's optimistic sets and the pending queue until it syncs — and
/// those are exactly the ones this screen exists to protect, so it must not
/// depend on the server it's insuring you against.
struct RatedRolesView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss
    @State private var wiped: [DismissedRole] = []
    @State private var wipedCompanies: [DismissedCompany] = []
    @State private var kept: [Role] = []
    @State private var loading = true
    @State private var loadError: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if loading {
                    ProgressView().tint(Theme.rust).frame(maxWidth: .infinity).padding(.top, 40)
                } else if let loadError {
                    Text(loadError).font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                } else if wiped.isEmpty && wipedCompanies.isEmpty && kept.isEmpty {
                    Text("Nothing wiped or kept yet. Swipe a few roles and they'll show up here.")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                } else {
                    if !store.pending.isEmpty {
                        Text("\(store.pending.count) change\(store.pending.count == 1 ? "" : "s") still waiting to sync.")
                            .font(.caption).foregroundStyle(Theme.rust).reconCard(10)
                    }

                    if !wipedCompanies.isEmpty {
                        SectionHeader(title: "Employers you never want to see",
                                      trailing: "\(wipedCompanies.count)")
                        ForEach(wipedCompanies) { co in
                            HStack {
                                Text(co.name).font(.subheadline.weight(.semibold))
                                    .foregroundStyle(Theme.ink)
                                Spacer()
                                Button {
                                    Task {
                                        await store.undismissCompany(co.id)
                                        await load()
                                    }
                                } label: {
                                    Label("Undo", systemImage: "arrow.uturn.backward")
                                        .font(.caption.weight(.medium))
                                }
                                .foregroundStyle(Theme.rust)
                            }
                            .reconCard()
                        }
                    }

                    if !kept.isEmpty {
                        SectionHeader(title: "Kept", trailing: "\(kept.count)")
                        ForEach(kept) { role in
                            RoleRow(role: role)
                        }
                    }

                    if !wiped.isEmpty {
                        SectionHeader(title: "Wiped", trailing: "\(wiped.count)")
                        ForEach(wiped) { role in
                            VStack(alignment: .leading, spacing: 8) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(role.company ?? "—")
                                        .font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                                    Text(role.title).font(.callout).foregroundStyle(Theme.ink).lineLimit(2)
                                    if let loc = role.location, !loc.isEmpty {
                                        Label(loc, systemImage: "mappin.and.ellipse")
                                            .font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(1)
                                    }
                                }
                                Button {
                                    Task {
                                        await store.undismiss(role.id)
                                        await load()
                                    }
                                } label: {
                                    Label("Undo — put back in the feed", systemImage: "arrow.uturn.backward")
                                        .font(.caption.weight(.medium))
                                }
                                .foregroundStyle(Theme.rust)
                            }
                            .reconCard()
                        }
                    }
                }
            }
            .padding(16)
        }
        .reconBackground()
        .navigationTitle("Wiped & kept")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .refreshable { await load() }
    }

    private func load() async {
        // Local first: anything wiped while offline exists only here.
        var localWiped: [DismissedRole] = store.roles
            .filter { store.hiddenRoleIds.contains($0.id) }
            .map { DismissedRole(id: $0.id, title: $0.title, company: $0.company,
                                 companyId: $0.companyId, location: $0.location,
                                 url: $0.url, dismissedAt: nil) }
        kept = store.roles.filter { store.likedRoleIds.contains($0.id) }

        var fetchFailed: String?
        do {
            let server = try await ReconAPI.shared.dismissedRoles()
            let known = Set(localWiped.map(\.id))
            localWiped += server.filter { !known.contains($0.id) }
            wipedCompanies = try await ReconAPI.shared.dismissedCompanies()
        } catch {
            fetchFailed = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            // Companies wiped offline still deserve a row, even with no name
            // from the server — fall back to whatever the cached roles know.
            if wipedCompanies.isEmpty {
                let names = Dictionary(store.roles.compactMap { r -> (Int, String)? in
                    guard let cid = r.companyId, let n = r.company else { return nil }
                    return (cid, n)
                }, uniquingKeysWith: { a, _ in a })
                wipedCompanies = store.dismissedCompanyIds.map {
                    DismissedCompany(id: $0, name: names[$0] ?? "Company \($0)", dismissedAt: nil)
                }
            }
        }
        wiped = localWiped
        loadError = (wiped.isEmpty && kept.isEmpty && wipedCompanies.isEmpty) ? fetchFailed : nil
        loading = false
    }
}
