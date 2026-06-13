import SwiftUI

/// Compact internship card: company, tier, fit, PAY, and a one-line summary.
struct RoleRow: View {
    let role: Role
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                TierChip(tier: role.tier)
                Text(role.company ?? "—").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Spacer()
                Label(role.fitText, systemImage: "target")
                    .font(.caption.weight(.semibold)).foregroundStyle(Theme.fit(role.fitScore))
            }
            Text(role.title).font(.callout).foregroundStyle(Theme.ink).lineLimit(2)
            HStack(spacing: 10) {
                Label(role.pay, systemImage: "dollarsign.circle")
                    .font(.caption).foregroundStyle(Theme.green).lineLimit(1)
                if let loc = role.location, !loc.isEmpty {
                    Label(loc, systemImage: "mappin.and.ellipse")
                        .font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(1)
                }
            }
            Text(role.summary).font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(2)
        }
        .reconCard()
    }
}

struct TierChip: View {
    let tier: String?
    var body: some View {
        Text((tier ?? "?").uppercased())
            .font(.caption2.weight(.bold)).foregroundStyle(.white)
            .padding(.horizontal, 7).padding(.vertical, 3)
            .background(Theme.tier(tier), in: Capsule())
    }
}

/// The scored feed, segmented by track (internships vs full-time) and fit tier.
struct RolesView: View {
    @EnvironmentObject var store: Store
    @State private var track: String = "intern"
    @State private var filter: String = "All"
    private let filters = ["All", "A", "B", "C"]

    var trackFeed: [Role] { track == "intern" ? store.internFeed : store.fulltimeFeed }
    var shown: [Role] {
        filter == "All" ? trackFeed
            : trackFeed.filter { ($0.tier ?? "").uppercased() == filter }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let err = store.error { ErrorBanner(message: err) }
                Picker("Track", selection: $track) {
                    Text("Internships (\(store.internFeed.count))").tag("intern")
                    Text("Full-time (\(store.fulltimeFeed.count))").tag("fulltime")
                }.pickerStyle(.segmented)
                Picker("Tier", selection: $filter) {
                    ForEach(filters, id: \.self) { Text($0) }
                }.pickerStyle(.segmented)

                if shown.isEmpty {
                    Text(track == "intern"
                         ? "No internships in this tier yet. Most Summer 2027 reqs post Aug 2026–Jan 2027."
                         : "No full-time product roles in this tier right now.")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                } else {
                    ForEach(shown) { role in
                        NavigationLink(value: role) { RoleRow(role: role) }.buttonStyle(.plain)
                    }
                }
            }
            .padding(16)
        }
        .navigationDestination(for: Role.self) { RoleDetailView(role: $0) }
        .scrollContentBackground(.hidden)
    }
}

/// Full detail for one internship.
struct RoleDetailView: View {
    let role: Role
    @EnvironmentObject var store: Store
    @State private var tracked = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 8) {
                    HStack { TierChip(tier: role.tier)
                        Text(role.company ?? "—").font(.headline).foregroundStyle(Theme.ink)
                        Spacer()
                        Text("fit \(role.fitText)").font(.subheadline.weight(.semibold))
                            .foregroundStyle(Theme.fit(role.fitScore))
                    }
                    Text(role.title).font(.title3.weight(.semibold)).foregroundStyle(Theme.ink)
                }

                facts

                Section_("Why it fits", role.summary)
                if let c = role.concerns, !c.isEmpty { Section_("Concerns", c, tint: Theme.rust) }
                if let h = role.curriculumHook, !h.isEmpty { Section_("Curriculum hook", h) }

                HStack(spacing: 12) {
                    if let urlStr = role.url, let url = URL(string: urlStr) {
                        Link(destination: url) {
                            Label("Open posting", systemImage: "safari")
                                .frame(maxWidth: .infinity)
                        }.buttonStyle(.borderedProminent).tint(Theme.rust)
                    }
                    Button {
                        Task { await store.track(role); tracked = true }
                    } label: {
                        Label(tracked ? "Tracking" : "Track", systemImage: tracked ? "checkmark" : "plus")
                            .frame(maxWidth: .infinity)
                    }.buttonStyle(.bordered).tint(Theme.green).disabled(tracked)
                }
            }
            .padding(16)
        }
        .background(Theme.paper.ignoresSafeArea())
        .navigationTitle(role.company ?? "Role")
        .navigationBarTitleDisplayMode(.inline)
        .scrollContentBackground(.hidden)
    }

    private var facts: some View {
        VStack(spacing: 0) {
            FactRow("Pay", role.pay, tint: Theme.green)
            Divider().background(Theme.hair)
            FactRow("Location", role.location ?? "—")
            Divider().background(Theme.hair)
            FactRow("Domain", role.domain ?? "—")
            Divider().background(Theme.hair)
            FactRow("Product PM?", (role.isProductPm == true) ? "Yes" : "No",
                    tint: role.isProductPm == true ? Theme.green : Theme.rust)
        }
        .reconCard()
    }

    private func Section_(_ title: String, _ body: String, tint: Color = Theme.ink) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title.uppercased()).font(.caption2.weight(.bold)).foregroundStyle(Theme.inkSoft)
            Text(body).font(.callout).foregroundStyle(tint)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct FactRow: View {
    let k: String; let v: String; var tint: Color = Theme.ink
    init(_ k: String, _ v: String, tint: Color = Theme.ink) { self.k = k; self.v = v; self.tint = tint }
    var body: some View {
        HStack {
            Text(k).font(.subheadline).foregroundStyle(Theme.inkSoft)
            Spacer()
            Text(v).font(.subheadline.weight(.medium)).foregroundStyle(tint)
                .multilineTextAlignment(.trailing)
        }.padding(.vertical, 9)
    }
}
