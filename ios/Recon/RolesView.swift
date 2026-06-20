import SwiftUI

/// Compact internship card: company, tier, fit, PAY, and a one-line summary.
struct RoleRow: View {
    let role: Role
    var body: some View {
        HStack(spacing: 0) {
            // tier-colored editorial accent edge
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .fill(Theme.tier(role.tier))
                .frame(width: 4)
                .padding(.vertical, 2)

            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    TierChip(tier: role.tier)
                    Text(role.company ?? "—").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                    Spacer()
                    FitBadge(score: role.fitScore, text: role.fitText)
                }
                Text(role.title).font(.callout).foregroundStyle(Theme.ink).lineLimit(2)
                HStack(spacing: 10) {
                    Label(role.pay, systemImage: "dollarsign.circle")
                        .font(.caption).foregroundStyle(Theme.green).lineLimit(1)
                    if let loc = role.location, !loc.isEmpty {
                        Label(loc, systemImage: "mappin.and.ellipse")
                            .font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(1)
                    }
                    if let posted = role.postedText {
                        Label(posted, systemImage: "clock")
                            .font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(1)
                    }
                }
                Text(role.summary).font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(2)
            }
            .padding(.leading, 12)
        }
        .reconCard()
    }
}

/// Fit score as a soft, color-coded capsule — stronger scan signal than plain text.
struct FitBadge: View {
    let score: Double?
    let text: String
    var body: some View {
        let color = Theme.fit(score)
        return Label("fit \(text)", systemImage: "target")
            .font(.caption2.weight(.bold)).foregroundStyle(color)
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(color.opacity(0.13), in: Capsule())
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

    var trackFeed: [Role] {
        switch track {
        case "fulltime": return store.fulltimeFeed
        case "ops":      return store.opsFeed
        default:         return store.internFeed
        }
    }
    var shown: [Role] {
        filter == "All" ? trackFeed
            : trackFeed.filter { ($0.tier ?? "").uppercased() == filter }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let err = store.error { ErrorBanner(message: err) }
                Picker("Track", selection: $track) {
                    Text("Intern (\(store.internFeed.count))").tag("intern")
                    Text("Full-time (\(store.fulltimeFeed.count))").tag("fulltime")
                    Text("Ops (\(store.opsFeed.count))").tag("ops")
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
    @State private var showTailor = false
    @State private var showOutreach = false
    @State private var showPrep = false
    @State private var showCover = false
    @State private var showNetwork = false
    @State private var matRefresh = 0
    @State private var companyContacts: [Contact] = []

    /// levels.fyi has no public API, so deep-link a search for the company.
    private var levelsURL: URL? {
        guard let co = role.company,
              let q = co.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)
        else { return nil }
        return URL(string: "https://www.levels.fyi/?search=\(q)")
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 8) {
                    HStack { TierChip(tier: role.tier)
                        Text(role.company ?? "—").font(.headline).foregroundStyle(Theme.ink)
                        Spacer()
                        FitBadge(score: role.fitScore, text: role.fitText)
                    }
                    Text(role.title).font(.title3.weight(.semibold)).foregroundStyle(Theme.ink)
                }

                facts

                Section_("Why it fits", role.summary)
                if let c = role.concerns, !c.isEmpty { Section_("Concerns", c, tint: Theme.rust) }
                if let h = role.curriculumHook, !h.isEmpty { Section_("Curriculum hook", h) }

                if !companyContacts.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("WHO YOU KNOW AT \((role.company ?? "").uppercased())")
                            .font(.caption2.weight(.bold)).foregroundStyle(Theme.inkSoft)
                        ForEach(companyContacts) { c in
                            HStack(spacing: 6) {
                                Image(systemName: "person.crop.circle").foregroundStyle(Theme.rust)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(c.name ?? "—").font(.caption.weight(.semibold)).foregroundStyle(Theme.ink)
                                    if let r = c.role { Text(r).font(.caption2).foregroundStyle(Theme.inkSoft) }
                                }
                                Spacer()
                                Pill(text: c.statusLabel, color: Theme.gold)
                            }
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).reconCard()
                }

                Button { showTailor = true } label: {
                    Label("Tailor my résumé to this role", systemImage: "wand.and.stars")
                }.buttonStyle(ReconButtonStyle(color: Theme.gold))

                Button { showNetwork = true } label: {
                    Label("Who to reach out to", systemImage: "person.2.badge.gearshape")
                }.buttonStyle(ReconButtonStyle(color: Theme.rust))

                Button { showOutreach = true } label: {
                    Label("Draft outreach", systemImage: "envelope")
                }.buttonStyle(ReconButtonStyle(color: Theme.rust, soft: true))

                Button { showPrep = true } label: {
                    Label("Interview prep", systemImage: "person.2.wave.2")
                }.buttonStyle(ReconButtonStyle(color: Theme.green, soft: true))

                Button { showCover = true } label: {
                    Label("Cover letter", systemImage: "doc.text")
                }.buttonStyle(ReconButtonStyle(color: Theme.gold, soft: true))

                MaterialsCard(role: role, refresh: matRefresh)

                if let levels = levelsURL {
                    Link(destination: levels) {
                        Label("Check comp on levels.fyi", systemImage: "chart.bar")
                    }.buttonStyle(ReconButtonStyle(color: Theme.inkSoft, soft: true))
                }

                HStack(spacing: 12) {
                    if let urlStr = role.url, let url = URL(string: urlStr) {
                        Link(destination: url) {
                            Label("Open posting", systemImage: "safari")
                                .frame(maxWidth: .infinity)
                        }.buttonStyle(.bordered).tint(Theme.rust)
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
        .background(Theme.canvas.ignoresSafeArea())
        .navigationTitle(role.company ?? "Role")
        .navigationBarTitleDisplayMode(.inline)
        .scrollContentBackground(.hidden)
        .sheet(isPresented: $showTailor, onDismiss: { matRefresh += 1 }) { TailorView(role: role).environmentObject(store) }
        .sheet(isPresented: $showOutreach, onDismiss: { matRefresh += 1 }) { OutreachView(role: role).environmentObject(store) }
        .sheet(isPresented: $showPrep, onDismiss: { matRefresh += 1 }) { InterviewPrepView(role: role).environmentObject(store) }
        .sheet(isPresented: $showCover, onDismiss: { matRefresh += 1 }) { CoverLetterView(role: role).environmentObject(store) }
        .sheet(isPresented: $showNetwork) { NetworkingView(role: role).environmentObject(store) }
        .task {
            if let co = role.company {
                companyContacts = (try? await ReconAPI.shared.contacts(company: co)) ?? []
            }
        }
    }

    private var facts: some View {
        VStack(spacing: 0) {
            FactRow("Pay", role.pay, tint: Theme.green)
            Divider().background(Theme.hair)
            FactRow("Posted", role.postedText ?? "—")
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
