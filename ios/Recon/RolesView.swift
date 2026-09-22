import SwiftUI

/// Compact internship card: company, tier, fit, PAY, and a one-line summary.
/// One role, as a card.
///
/// Redesigned 2026-09-21. The old card spent its two best lines on the JD's
/// opening sentence, which is marketing boilerplate on nearly every posting
/// ("X is the trusted platform to industrialize enterprise AI"), and buried the
/// facts that actually decide whether to open it. A card now answers, in order:
/// is it new, who is it, what is it, when is it for, where is it, when did it
/// appear.
struct RoleRow: View {
    let role: Role
    var isNew: Bool = false

    private var accent: Color {
        if role.isNewToday { return Theme.gold }
        if role.isBackfill == true { return Theme.hair }
        return Theme.hair
    }

    var body: some View {
        HStack(spacing: 0) {
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .fill(accent)
                .frame(width: 4)
                .padding(.vertical, 2)

            VStack(alignment: .leading, spacing: 7) {
                // Who, and whether it's new.
                HStack(spacing: 8) {
                    if role.isNewToday { Pill(text: "New", color: Theme.gold, filled: true) }
                    Text(role.company ?? "—")
                        .font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                    Spacer()
                    Text(role.dateLabel)
                        .font(.caption2.weight(role.isNewToday ? .semibold : .regular))
                        .foregroundStyle(role.isNewToday ? Theme.gold : Theme.inkSoft)
                        .lineLimit(1)
                }

                // What.
                Text(role.title).font(.callout.weight(.medium))
                    .foregroundStyle(Theme.ink).lineLimit(2)

                // When it's for, and who it's for — the two facts that rule an
                // internship in or out fastest.
                HStack(spacing: 6) {
                    if let term = role.termLabel { Pill(text: term, color: Theme.rust) }
                    if role.isMba == true { Pill(text: "MBA", color: Theme.rust) }
                    if role.remote == true { Pill(text: "Remote", color: Theme.green) }
                    if role.isBackfill == true { Pill(text: "backlog", color: Theme.inkSoft) }
                }

                // Where, and pay when there is one.
                HStack(spacing: 10) {
                    if let loc = role.location, !loc.isEmpty {
                        Label(loc.replacingOccurrences(of: ";", with: " · "),
                              systemImage: "mappin.and.ellipse")
                            .font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(1)
                    }
                    if let pay = role.tcEstimate, !pay.isEmpty {
                        Label(pay, systemImage: "dollarsign.circle")
                            .font(.caption).foregroundStyle(Theme.green).lineLimit(1)
                    }
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
    /// What this tab is showing. The old track picker (intern / full-time /
    /// ops) is gone: the server sends only in-track roles, so two of its three
    /// segments were permanently zero. The useful split is by *state of the
    /// search*, not by track.
    enum Segment: String, CaseIterable, Identifiable {
        case live, new, saved
        var id: String { rawValue }
        var label: String {
            switch self {
            case .live:  return "Live"
            case .new:   return "New"
            case .saved: return "Saved"
            }
        }
    }
    @State private var segment: Segment = .live
    @State private var selectedStates: Set<String> = []   // empty = all locations; multi-select
    @State private var showStateFilter = false
    @State private var sector: String? = nil      // nil = all sectors
    @State private var mbaOnly: Bool = false
    @State private var showSwipe = false
    @State private var wipedNotice: String?
    @State private var newWithinDays: Int = 7       // the "New" segment's window
    @State private var query: String = ""
    /// Target-metro slug -> display label (mirrors api/scan/geo.py METROS). Still
    /// used for the RoleDetailView "target metro" callout — the browse/filter UI
    /// below uses the exhaustive state list instead (2026-08-16).
    static let metroLabels: [(String, String)] = [
        ("charleston", "Charleston"), ("nyc", "NYC"), ("dc_metro", "DC / NoVA / MD"),
        ("socal", "SoCal"), ("boston", "Boston"), ("pennsylvania", "Pennsylvania"),
        ("rtp", "Raleigh-Durham"), ("bay_area", "SF Bay Area"),
        ("remote", "Remote (US)"),
    ]

    /// The segment's base list, before the facets.
    var trackFeed: [Role] {
        switch segment {
        case .live:  return store.feed
        case .new:   return store.newWithin(days: newWithinDays)
        case .saved: return store.feed.filter { store.interest(of: $0) == "up" }
        }
    }
    var shown: [Role] {
        trackFeed.filter {
            (selectedStates.isEmpty || !selectedStates.isDisjoint(with: $0.stateCodes))
            && (sector == nil || $0.sector == sector)
            && (!mbaOnly || $0.isMba == true)
            && matchesQuery($0)
        }
    }
    private func matchesQuery(_ r: Role) -> Bool {
        let q = query.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { return true }
        return r.title.localizedCaseInsensitiveContains(q)
            || (r.company ?? "").localizedCaseInsensitiveContains(q)
            || (r.location ?? "").localizedCaseInsensitiveContains(q)
    }

    private var stateFilterLabel: String {
        switch selectedStates.count {
        case 0: return "All locations"
        case 1: return Role.stateLabels.first { $0.0 == selectedStates.first }?.1 ?? selectedStates.first!
        default: return "\(selectedStates.count) locations"
        }
    }
    private var emptyMessage: String {
        if !query.isEmpty { return "Nothing matches \"\(query)\"." }
        if !selectedStates.isEmpty { return "Nothing open in \(stateFilterLabel) right now." }
        switch segment {
        case .new:
            return "Nothing new in this window. Recon scans hourly and counts a posting as new when the board dates it today — or when it appears on a board that doesn't publish dates."
        case .saved:
            return "Nothing saved yet. Tap Keep on a role, or swipe right in triage."
        case .live:
            return "No internships open yet. Most Summer 2027 reqs post Aug 2026–Jan 2027 — Recon scans hourly."
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
                Picker("Segment", selection: $segment) {
                    Text("Live (\(store.feed.count))").tag(Segment.live)
                    Text("New (\(store.newWithin(days: newWithinDays).count))").tag(Segment.new)
                    Text("Saved (\(store.likedRoleIds.count))").tag(Segment.saved)
                }.pickerStyle(.segmented)

                // The "New" window. Only shown where it applies — a window
                // control over the whole live board would just be noise.
                if segment == .new {
                    HStack(spacing: 8) {
                        ForEach([(1, "Today"), (3, "3 days"), (7, "This week"), (30, "30 days")], id: \.0) { days, label in
                            Button { newWithinDays = days } label: {
                                Text(label).font(.caption.weight(.medium))
                                    .padding(.horizontal, 11).padding(.vertical, 7)
                                    .foregroundStyle(newWithinDays == days ? .white : Theme.ink)
                                    .background(newWithinDays == days ? Theme.rust : Theme.card,
                                                in: Capsule())
                                    .overlay(Capsule().stroke(Theme.hair))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }

                HStack(spacing: 6) {
                    Image(systemName: "magnifyingglass").font(.caption).foregroundStyle(Theme.inkSoft)
                    TextField("Search title, company, location", text: $query)
                        .font(.subheadline).textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    if !query.isEmpty {
                        Button { query = "" } label: {
                            Image(systemName: "xmark.circle.fill").foregroundStyle(Theme.inkSoft)
                        }.buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 12).padding(.vertical, 9)
                .background(Theme.card, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(Theme.hair))
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

                    do {
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
                    Text(emptyMessage)
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
                if role.hasUsefulDescription {
                    JobDescriptionCard(role: role)
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


/// The job description, readably.
///
/// It used to render the list payload under the heading "Full job description".
/// That payload is truncated to 600 characters server-side, so the heading was a
/// lie and the text usually stopped mid-sentence. The full JD lives behind
/// `/api/roles/{id}`, which nothing was calling; this fetches it the first time
/// the reader asks to see more, and shows a preview until then.
struct JobDescriptionCard: View {
    let role: Role
    @State private var expanded = false
    @State private var full: String?
    @State private var loading = false

    /// The preview always comes from what we already have — no spinner to read
    /// the first few lines.
    private var preview: String { (role.description ?? "").decodingHTMLEntities }
    private var body_: String { full?.decodingHTMLEntities ?? preview }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("JOB DESCRIPTION")
                .font(.caption2.weight(.bold)).foregroundStyle(Theme.inkSoft)

            Text(body_)
                .font(.callout)
                .foregroundStyle(Theme.ink)
                .lineSpacing(3)
                .lineLimit(expanded ? nil : 6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .animation(.easeInOut(duration: 0.15), value: expanded)

            HStack(spacing: 10) {
                Button(expanded ? "Show less" : "Show more") {
                    expanded.toggle()
                    if expanded { Task { await loadFull() } }
                }
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.rust)

                if loading {
                    ProgressView().controlSize(.mini)
                }
                Spacer()
            }
            .buttonStyle(.plain)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .reconCard()
    }

    /// Fetch once, and treat failure as "keep the preview" — an unreachable
    /// server shouldn't blank out text we already had in hand.
    private func loadFull() async {
        guard full == nil, !loading else { return }
        loading = true
        defer { loading = false }
        if let text = try? await ReconAPI.shared.fullDescription(roleId: role.id),
           text.count > preview.count {
            full = text
        }
    }
}
