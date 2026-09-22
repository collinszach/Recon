import SwiftUI

/// Compact internship card: company, tier, fit, PAY, and a one-line summary.
struct RoleRow: View {
    let role: Role
    var isNew: Bool = false
    var body: some View {
        HStack(spacing: 0) {
            // Editorial accent edge. Used to be the fit tier; with scoring off
            // (2026-09-21) recency is the signal that's actually left.
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .fill(isNew ? Theme.gold : Theme.hair)
                .frame(width: 4)
                .padding(.vertical, 2)

            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    if isNew { Pill(text: "New", color: Theme.gold, filled: true) }
                    if role.isMba == true { Pill(text: "MBA", color: Theme.rust) }
                    Text(role.company ?? "—").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                    if role.isBackfill == true { Pill(text: "backlog", color: Theme.inkSoft) }
                    Spacer()
                }
                Text(role.title).font(.callout).foregroundStyle(Theme.ink).lineLimit(2)
                HStack(spacing: 10) {
                    // Posting age leads: it's the signal that decides whether a
                    // role is worth opening, and an undated one says so plainly
                    // instead of looking fresh.
                    Label(role.dateLabel, systemImage: role.postedIsKnown ? "calendar" : "questionmark.circle")
                        .font(.caption.weight(role.postedToday ? .semibold : .regular))
                        .foregroundStyle(role.postedToday ? Theme.gold
                                         : (role.postedIsKnown ? Theme.inkSoft : Theme.inkSoft.opacity(0.7)))
                        .lineLimit(1)
                    if let loc = role.location, !loc.isEmpty {
                        Label(loc, systemImage: "mappin.and.ellipse")
                            .font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(1)
                    }
                    // Pay only when there is one. "Pay not listed" was on
                    // essentially every row — a whole line spent saying nothing.
                    if let pay = role.tcEstimate, !pay.isEmpty {
                        Label(pay, systemImage: "dollarsign.circle")
                            .font(.caption).foregroundStyle(Theme.green).lineLimit(1)
                    }
                }
                // The JD's opening line, when there is one. This used to be
                // `role.summary` — the scorer's why_fit — which on the old
                // rule-scored internships is the canned "Rule-based heuristic
                // score — no strong signal either way." repeated on every card.
                if let blurb = role.blurb {
                    Text(blurb).font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(2)
                }
            }
            .padding(.leading, 12)
        }
        .reconCard()
    }
}

/// The tracker feed. Scoring is off, so there are no tiers or fit scores to
/// filter on — what's left is location, sector, MBA-track, and how new it is.
struct RolesView: View {
    @EnvironmentObject var store: Store
    @State private var track: String = "intern"
    @State private var selectedStates: Set<String> = []   // empty = all locations; multi-select
    @State private var showStateFilter = false
    @State private var sector: String? = nil      // nil = all sectors
    @State private var mbaOnly: Bool = false
    @State private var showSwipe = false
    @State private var wipedNotice: String?
    @State private var postedWithin: Int? = nil     // days; nil = any age
    /// Target-metro slug -> display label (mirrors api/scan/geo.py METROS). Still
    /// used for the RoleDetailView "target metro" callout — the browse/filter UI
    /// below uses the exhaustive state list instead (2026-08-16).
    static let metroLabels: [(String, String)] = [
        ("charleston", "Charleston"), ("nyc", "NYC"), ("dc_metro", "DC / NoVA / MD"),
        ("socal", "SoCal"), ("boston", "Boston"), ("pennsylvania", "Pennsylvania"),
        ("rtp", "Raleigh-Durham"), ("bay_area", "SF Bay Area"),
        ("remote", "Remote (US)"),
    ]

    var trackFeed: [Role] {
        switch track {
        case "fulltime": return store.fulltimeFeed
        case "ops":      return store.opsFeed
        default:         return store.internFeed
        }
    }
    var shown: [Role] {
        trackFeed.filter {
            (postedWithin == nil || withinPosted($0, days: postedWithin!))
            && (selectedStates.isEmpty || !selectedStates.isDisjoint(with: $0.stateCodes))
            && (sector == nil || $0.sector == sector)
            && (!mbaOnly || $0.isMba == true)
        }
    }
    /// Posted within N days. Strict: an undated role never counts as recent,
    /// the same rule the dashboard's "posted today" uses.
    private func withinPosted(_ role: Role, days: Int) -> Bool {
        guard let d = role.postedDate else { return false }
        return d >= Date().addingTimeInterval(-Double(days) * 86_400)
    }

    private var stateFilterLabel: String {
        switch selectedStates.count {
        case 0: return "All locations"
        case 1: return Role.stateLabels.first { $0.0 == selectedStates.first }?.1 ?? selectedStates.first!
        default: return "\(selectedStates.count) locations"
        }
    }
    private var sectorLabel: String {
        guard let s = sector else { return "All sectors" }
        return Role.sectorLabels.first { $0.0 == s }?.1 ?? s
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let err = store.error { ErrorBanner(message: err) }
                // Posting-age chips. "Any age" is the default because the
                // board backlog is legitimately most of the feed.
                HStack(spacing: 8) {
                    ForEach([(nil as Int?, "Any age"), (1, "Today"), (3, "3 days"), (7, "This week")], id: \.1) { days, label in
                        Button { postedWithin = (postedWithin == days ? nil : days) } label: {
                            Text(label).font(.caption.weight(.medium))
                                .padding(.horizontal, 11).padding(.vertical, 7)
                                .foregroundStyle(postedWithin == days ? .white : Theme.ink)
                                .background(postedWithin == days ? Theme.rust : Theme.card,
                                            in: Capsule())
                                .overlay(Capsule().stroke(Theme.hair))
                        }
                        .buttonStyle(.plain)
                    }
                }

                Picker("Track", selection: $track) {
                    Text("Intern (\(store.internFeed.count))").tag("intern")
                    Text("Full-time (\(store.fulltimeFeed.count))").tag("fulltime")
                    Text("Ops (\(store.opsFeed.count))").tag("ops")
                }.pickerStyle(.segmented)
                // Geo facet: every US state + remote + international (exhaustive —
                // 2026-08-16, replacing the old hand-picked metro-only list which
                // always missed somewhere, e.g. Denver/CO). Multi-select via a sheet
                // since Menu dismisses on every tap, which doesn't work for picking
                // more than one.
                Button {
                    showStateFilter = true
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "mappin.and.ellipse")
                        Text(stateFilterLabel).font(.subheadline.weight(.medium))
                        Image(systemName: "chevron.down").font(.caption2)
                        Spacer()
                        if !selectedStates.isEmpty {
                            Text("\(shown.count)").font(.caption.weight(.bold))
                                .foregroundStyle(Theme.inkSoft)
                        }
                    }
                    .foregroundStyle(Theme.ink)
                    .padding(.horizontal, 12).padding(.vertical, 9)
                    .background(Theme.card, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(Theme.hair))
                }
                .sheet(isPresented: $showStateFilter) {
                    StateFilterSheet(selected: $selectedStates, trackFeed: trackFeed)
                }

                // Sector facet (Big Tech / Finance / Defense-Aerospace / Consulting)
                // + MBA-track toggle — both rule-based, zero AI cost (2026-08-15).
                HStack(spacing: 8) {
                    Menu {
                        Button { sector = nil } label: {
                            Label("All sectors (\(trackFeed.count))",
                                  systemImage: sector == nil ? "checkmark" : "")
                        }
                        ForEach(Role.sectorLabels, id: \.0) { slug, label in
                            let n = trackFeed.filter { $0.sector == slug }.count
                            Button { sector = slug } label: {
                                Label("\(label) (\(n))", systemImage: sector == slug ? "checkmark" : "")
                            }.disabled(n == 0)
                        }
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "building.2")
                            Text(sectorLabel).font(.subheadline.weight(.medium))
                            Image(systemName: "chevron.down").font(.caption2)
                        }
                        .foregroundStyle(Theme.ink)
                        .padding(.horizontal, 12).padding(.vertical, 9)
                        .background(Theme.card, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(Theme.hair))
                    }

                    if track == "intern" {
                        let mbaCount = trackFeed.filter { $0.isMba == true }.count
                        Button { mbaOnly.toggle() } label: {
                            Label("MBA (\(mbaCount))", systemImage: mbaOnly ? "checkmark.circle.fill" : "circle")
                                .font(.subheadline.weight(.medium))
                        }
                        .foregroundStyle(mbaOnly ? .white : Theme.ink)
                        .padding(.horizontal, 12).padding(.vertical, 9)
                        .background(mbaOnly ? Theme.rust : Theme.card,
                                   in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(Theme.hair))
                        .disabled(mbaCount == 0 && !mbaOnly)
                    }
                }

                if let notice = wipedNotice {
                    Text(notice).font(.footnote).foregroundStyle(Theme.inkSoft).reconCard()
                }
                if shown.isEmpty {
                    Text(!selectedStates.isEmpty
                         ? "Nothing open in \(stateFilterLabel) right now."
                         : (track == "intern"
                            ? "No internships open yet. Most Summer 2027 reqs post Aug 2026–Jan 2027 — Recon scans hourly."
                            : "Nothing open in this track right now."))
                        .font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                } else {
                    ForEach(shown) { role in
                        NavigationLink(value: role) { RoleRow(role: role, isNew: role.firstSeenIsToday) }
                            .buttonStyle(.plain)
                            .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                Button(role: .destructive) {
                                    Task { await store.dismiss(role) }
                                } label: { Label("Wipe", systemImage: "trash") }
                            }
                            .contextMenu {
                                Button(role: .destructive) {
                                    Task { await store.dismiss(role) }
                                } label: { Label("Wipe this role", systemImage: "trash") }
                                if let cid = role.companyId, let name = role.company {
                                    Button(role: .destructive) {
                                        Task {
                                            let n = await store.dismissCompany(cid)
                                            wipedNotice = "Wiped \(name) — \(n) role\(n == 1 ? "" : "s") removed."
                                        }
                                    } label: {
                                        Label("Never show \(name)", systemImage: "building.2.crop.circle.badge.xmark")
                                    }
                                }
                            }
                    }
                }
            }
            .padding(16)
        }
        .navigationDestination(for: Role.self) { RoleDetailView(role: $0, store: store) }
        .scrollContentBackground(.hidden)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showSwipe = true } label: { Image(systemName: "hand.draw") }
                    .accessibilityLabel("Triage new roles")
            }
        }
        .fullScreenCover(isPresented: $showSwipe) {
            SwipeRateView(deck: store.unratedDeck(from: shown))
                .environmentObject(store)
        }
    }
}

/// Multi-select location picker — every US state + remote + international,
/// with live counts over the active track. A sheet (not a Menu) because Menu
/// dismisses on every tap, which breaks multi-select.
struct StateFilterSheet: View {
    @Binding var selected: Set<String>
    let trackFeed: [Role]
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""

    private var counts: [String: Int] {
        Dictionary(grouping: trackFeed.flatMap(\.stateCodes), by: { $0 }).mapValues(\.count)
    }
    private var rows: [(String, String)] {
        let all = Role.stateLabels.filter { counts[$0.0, default: 0] > 0 }
        guard !query.isEmpty else { return all }
        return all.filter { $0.1.localizedCaseInsensitiveContains(query) }
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Button {
                        selected.removeAll()
                    } label: {
                        HStack {
                            Text("All locations (\(trackFeed.count))")
                            Spacer()
                            if selected.isEmpty { Image(systemName: "checkmark").foregroundStyle(Theme.rust) }
                        }
                    }
                    .foregroundStyle(Theme.ink)
                    .listRowBackground(Theme.card)
                }
                Section {
                    ForEach(rows, id: \.0) { slug, label in
                        Button {
                            if selected.contains(slug) { selected.remove(slug) }
                            else { selected.insert(slug) }
                        } label: {
                            HStack {
                                Text("\(label) (\(counts[slug, default: 0]))")
                                Spacer()
                                if selected.contains(slug) { Image(systemName: "checkmark").foregroundStyle(Theme.rust) }
                            }
                        }
                        .foregroundStyle(Theme.ink)
                        .listRowBackground(Theme.card)
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .background(Theme.canvas.ignoresSafeArea())
            .searchable(text: $query, prompt: "Search locations")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                // Explicit principal title, not .navigationTitle() — the latter's
                // text color follows the system color scheme, which washed out to
                // near-invisible white-on-cream in dark mode since Theme's palette
                // is fixed/light-only. This guarantees the color regardless.
                ToolbarItem(placement: .principal) {
                    Text("Locations").font(.headline).foregroundStyle(Theme.ink)
                }
                ToolbarItem(placement: .cancellationAction) {
                    Button("Clear") { selected.removeAll() }.disabled(selected.isEmpty)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

/// Keep it or wipe it. "Wipe" is permanent — the role leaves the feed now and
/// stays gone when the scan re-ingests the same posting — so it's the one
/// action here that can't be undone by accident: the Dismissed screen is where
/// it comes back from.
struct InterestControl: View {
    let role: Role
    @ObservedObject var store: Store
    var body: some View {
        let cur = store.interest(of: role)
        HStack(spacing: 10) {
            Button { Task { await store.setInterest(role, cur == "up" ? nil : "up") } } label: {
                Label("Keep", systemImage: cur == "up" ? "bookmark.fill" : "bookmark")
                    .font(.subheadline.weight(.semibold))
                    .frame(maxWidth: .infinity).padding(.vertical, 10)
                    .foregroundStyle(cur == "up" ? .white : Theme.green)
                    .background(cur == "up" ? Theme.green : Theme.green.opacity(0.12),
                                in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            Button { Task { await store.dismiss(role) } } label: {
                Label("Wipe", systemImage: cur == "down" ? "trash.fill" : "trash")
                    .font(.subheadline.weight(.semibold))
                    .frame(maxWidth: .infinity).padding(.vertical, 10)
                    .foregroundStyle(cur == "down" ? .white : Theme.inkSoft)
                    .background(cur == "down" ? Theme.rust : Theme.rust.opacity(0.10),
                                in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
        }
        .buttonStyle(.plain)
        .animation(.easeOut(duration: 0.15), value: cur)
    }
}

private enum RoleSheet: Identifiable {
    case tailor, outreach, prep, cover, network
    case editContact(Contact)
    var id: String {
        switch self {
        case .tailor:             return "tailor"
        case .outreach:           return "outreach"
        case .prep:               return "prep"
        case .cover:              return "cover"
        case .network:            return "network"
        case .editContact(let c): return "contact-\(c.id ?? 0)"
        }
    }
}

struct RoleDetailView: View {
    let role: Role
    @ObservedObject var store: Store
    @State private var tracked = false
    @State private var activeSheet: RoleSheet?
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
                    HStack {
                        Text(role.company ?? "—").font(.headline).foregroundStyle(Theme.ink)
                        Spacer()
                        if let seen = role.firstSeenText {
                            Text("seen \(seen)").font(.caption).foregroundStyle(Theme.inkSoft)
                        }
                    }
                    Text(role.title).font(.title3.weight(.semibold)).foregroundStyle(Theme.ink)
                }

                InterestControl(role: role, store: store)

                facts

                // These three are all scorer output. Nothing written since
                // 2026-09-21 has them, but older roles still do — show them when
                // they exist rather than blanking history.
                if let w = role.whyFit, !w.isEmpty { Section_("Why it fits", w) }
                if let c = role.concerns, !c.isEmpty { Section_("Concerns", c, tint: Theme.rust) }
                if let h = role.curriculumHook, !h.isEmpty { Section_("Curriculum hook", h) }
                if let d = role.description, !d.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        DisclosureGroup {
                            Text(d).font(.caption).foregroundStyle(Theme.inkSoft)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.top, 6)
                        } label: {
                            Text("Full job description").font(.subheadline.weight(.semibold))
                                .foregroundStyle(Theme.ink)
                        }
                        .tint(Theme.rust)
                    }.frame(maxWidth: .infinity, alignment: .leading).reconCard()
                }

                if !companyContacts.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("WHO YOU KNOW AT \((role.company ?? "").uppercased())")
                            .font(.caption2.weight(.bold)).foregroundStyle(Theme.inkSoft)
                        ForEach(companyContacts) { c in
                            Button { activeSheet = .editContact(c) } label: {
                                HStack(spacing: 6) {
                                    Image(systemName: "person.crop.circle")
                                        .foregroundStyle(c.needsFollowUp ? Theme.rust : Theme.gold)
                                    VStack(alignment: .leading, spacing: 1) {
                                        Text(c.name ?? "—").font(.caption.weight(.semibold)).foregroundStyle(Theme.ink)
                                        if let r = c.role { Text(r).font(.caption2).foregroundStyle(Theme.inkSoft) }
                                        else if let co = c.company { Text(co).font(.caption2).foregroundStyle(Theme.inkSoft) }
                                    }
                                    Spacer()
                                    if c.needsFollowUp {
                                        Pill(text: c.nextTouchDue ? "Touch due" : "No reply · 5d+",
                                             color: Theme.rust, filled: true)
                                    } else {
                                        Pill(text: c.statusLabel, color: Theme.gold)
                                    }
                                }
                            }
                            .buttonStyle(.plain)
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).reconCard()
                }

                Button { activeSheet = .tailor } label: {
                    Label("Tailor my résumé to this role", systemImage: "wand.and.stars")
                }.buttonStyle(ReconButtonStyle(color: Theme.gold))

                Button { activeSheet = .network } label: {
                    Label("Who to reach out to", systemImage: "person.2.badge.gearshape")
                }.buttonStyle(ReconButtonStyle(color: Theme.rust))

                Button { activeSheet = .outreach } label: {
                    Label("Draft outreach", systemImage: "envelope")
                }.buttonStyle(ReconButtonStyle(color: Theme.rust, soft: true))

                Button { activeSheet = .prep } label: {
                    Label("Interview prep", systemImage: "person.2.wave.2")
                }.buttonStyle(ReconButtonStyle(color: Theme.green, soft: true))

                Button { activeSheet = .cover } label: {
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
        .sheet(item: $activeSheet) { sheet in
            switch sheet {
            case .tailor:
                TailorView(role: role).environmentObject(store)
                    .onDisappear { matRefresh += 1 }
            case .outreach:
                OutreachView(role: role).environmentObject(store)
                    .onDisappear { matRefresh += 1 }
            case .prep:
                InterviewPrepView(role: role).environmentObject(store)
                    .onDisappear { matRefresh += 1 }
            case .cover:
                CoverLetterView(role: role).environmentObject(store)
                    .onDisappear { matRefresh += 1 }
            case .network:
                NetworkingView(role: role).environmentObject(store)
            case .editContact(let c):
                ContactEditor(contact: c)
                    .environmentObject(store)
                    .onDisappear {
                        Task {
                            if let co = role.company {
                                companyContacts = (try? await ReconAPI.shared.contacts(company: co)) ?? []
                            }
                        }
                    }
            }
        }
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
            if let m = role.metro {
                Divider().background(Theme.hair)
                let label = RolesView.metroLabels.first { $0.0 == m }?.1 ?? m
                FactRow("Target metro", label, tint: Theme.green)
            }
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
