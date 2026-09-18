import SwiftUI

/// Startups Zach is tracking/researching across fintech, defense, sustainability/
/// energy, and product/tech/data — separate track from the job-role pipeline.
struct StartupsView: View {
    @State private var startups: [Startup] = []
    @State private var loading = true
    @State private var sectorFilter: String? = nil
    @State private var showAdd = false

    private let sectors: [(String?, String)] = [
        (nil, "All"), ("fintech", "Fintech"), ("defense", "Defense"),
        ("sustainability_energy", "Sustainability / Energy"), ("product_tech_data", "Product / Tech / Data"),
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(sectors, id: \.1) { sector, label in
                            Button {
                                sectorFilter = sector
                                Task { await load() }
                            } label: {
                                Pill(text: label, color: Theme.rust, filled: sectorFilter == sector)
                            }
                        }
                    }
                }
                if loading {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 40)
                } else if startups.isEmpty {
                    Text("No startups tracked yet. Tap + to add one.")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                } else {
                    ForEach(startups) { s in
                        NavigationLink(destination: StartupDetailView(startup: s, onChanged: { Task { await load() } })) {
                            StartupRow(startup: s)
                        }.buttonStyle(.plain)
                    }
                }
            }.padding(16)
        }
        .scrollContentBackground(.hidden).background(Theme.canvas.ignoresSafeArea())
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showAdd = true } label: { Image(systemName: "plus") }
            }
        }
        .sheet(isPresented: $showAdd) {
            AddStartupView { Task { await load() } }
        }
        .task { await load() }
    }

    private func load() async {
        loading = true
        startups = (try? await ReconAPI.shared.startups(sector: sectorFilter)) ?? []
        loading = false
    }
}

private struct StartupRow: View {
    let startup: Startup
    var body: some View {
        HStack(spacing: 0) {
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .fill(Theme.rust).frame(width: 4).padding(.vertical, 2)
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    Pill(text: startup.sectorLabel, color: Theme.gold)
                    Text(startup.name).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                    Spacer()
                    if startup.hasWriteup == true {
                        Image(systemName: "doc.text.fill").font(.caption).foregroundStyle(Theme.green)
                    }
                }
                if let o = startup.oneLiner, !o.isEmpty {
                    Text(o).font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(2)
                }
                if let loc = startup.hqLocation, !loc.isEmpty {
                    Label(loc, systemImage: "mappin.and.ellipse").font(.caption2).foregroundStyle(Theme.inkSoft)
                }
            }.padding(.leading, 12)
        }.reconCard()
    }
}

private struct AddStartupView: View {
    @Environment(\.dismiss) private var dismiss
    let onSaved: () -> Void

    @State private var name = ""
    @State private var sector = "fintech"
    @State private var hqLocation = ""
    @State private var website = ""
    @State private var oneLiner = ""
    @State private var notes = ""
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Startup") {
                    TextField("Name", text: $name)
                    Picker("Sector", selection: $sector) {
                        ForEach(Startup.sectors, id: \.self) { s in
                            Text(Startup(name: "", sector: s).sectorLabel).tag(s)
                        }
                    }
                    TextField("HQ location", text: $hqLocation)
                    TextField("Website", text: $website)
                }
                Section("Notes") {
                    TextField("One-liner", text: $oneLiner, axis: .vertical)
                    TextField("Notes", text: $notes, axis: .vertical)
                }
            }
            .navigationTitle("Add Startup").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(saving ? "Saving…" : "Save") { Task { await save() } }
                        .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty || saving)
                }
            }
        }
    }

    private func save() async {
        saving = true
        var s = Startup(name: name, sector: sector)
        s.hqLocation = hqLocation.isEmpty ? nil : hqLocation
        s.website = website.isEmpty ? nil : website
        s.oneLiner = oneLiner.isEmpty ? nil : oneLiner
        s.notes = notes.isEmpty ? nil : notes
        _ = try? await ReconAPI.shared.addStartup(s)
        saving = false
        onSaved()
        dismiss()
    }
}

struct StartupDetailView: View {
    let startup: Startup
    var onChanged: () -> Void = {}

    @State private var detail: Startup?
    @State private var contacts: [StartupContact] = []
    @State private var plan: NetworkingPlan?
    @State private var generatingWriteup = false
    @State private var researchingContacts = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header
                writeupSection
                contactsSection
            }.padding(16)
        }
        .scrollContentBackground(.hidden).background(Theme.canvas.ignoresSafeArea())
        .navigationTitle(startup.name).navigationBarTitleDisplayMode(.inline)
        .task {
            detail = (try? await ReconAPI.shared.startup(id: startup.id ?? 0)) ?? startup
            contacts = (try? await ReconAPI.shared.startupContacts(id: startup.id ?? 0)) ?? []
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Pill(text: startup.sectorLabel, color: Theme.gold)
                if let stage = detail?.stage ?? startup.stage, !stage.isEmpty { Pill(text: stage, color: Theme.rust) }
            }
            if let o = detail?.oneLiner ?? startup.oneLiner, !o.isEmpty {
                Text(o).font(.subheadline).foregroundStyle(Theme.ink)
            }
            if let loc = detail?.hqLocation ?? startup.hqLocation, !loc.isEmpty {
                Label(loc, systemImage: "mappin.and.ellipse").font(.caption).foregroundStyle(Theme.inkSoft)
            }
            if let f = detail?.fundingSummary, !f.isEmpty {
                Text(f).font(.caption).foregroundStyle(Theme.inkSoft)
            }
        }.frame(maxWidth: .infinity, alignment: .leading).reconCard()
    }

    private var writeupSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("IN-DEPTH WRITEUP").font(.caption2.weight(.bold)).tracking(0.6).foregroundStyle(Theme.inkSoft)
                Spacer()
                Button {
                    Task { await generateWriteup() }
                } label: {
                    Label(generatingWriteup ? "Generating…" : (detail?.writeupMarkdown == nil ? "Generate" : "Regenerate"),
                          systemImage: "sparkles")
                }.buttonStyle(ReconButtonStyle(color: Theme.rust, soft: true)).disabled(generatingWriteup)
            }
            if generatingWriteup {
                AILoadingView(steps: ["Researching the company…", "Reading the landscape…",
                                     "Weighing the fit…", "Writing it up…"])
            } else if let md = detail?.writeupMarkdown, !md.isEmpty {
                Text(md).font(.callout).foregroundStyle(Theme.ink).textSelection(.enabled)
            } else {
                Text("No writeup yet — generate one on demand. This calls Claude once and caches the result; it never runs automatically.")
                    .font(.caption).foregroundStyle(Theme.inkSoft)
            }
        }.frame(maxWidth: .infinity, alignment: .leading).reconCard()
    }

    private var contactsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("CONTACTS").font(.caption2.weight(.bold)).tracking(0.6).foregroundStyle(Theme.inkSoft)
                Spacer()
                Button {
                    Task { await researchContacts() }
                } label: {
                    Label(researchingContacts ? "Researching…" : "Who to reach out to", systemImage: "person.badge.plus")
                }.buttonStyle(ReconButtonStyle(color: Theme.green, soft: true)).disabled(researchingContacts)
            }
            ForEach(contacts) { c in
                VStack(alignment: .leading, spacing: 2) {
                    Text(c.name ?? "—").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                    if let r = c.role, !r.isEmpty { Text(r).font(.caption).foregroundStyle(Theme.inkSoft) }
                }.frame(maxWidth: .infinity, alignment: .leading).padding(10)
                    .background(Theme.paper2.opacity(0.5), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
            if researchingContacts {
                AILoadingView(steps: ["Finding the warmest path in…", "Mapping personas…"])
            } else if let plan {
                if let s = plan.summary, !s.isEmpty {
                    Text(s).font(.caption).foregroundStyle(Theme.inkSoft)
                }
                ForEach(plan.targets ?? []) { t in
                    StartupContactCard(startupId: startup.id ?? 0, target: t) {
                        Task { contacts = (try? await ReconAPI.shared.startupContacts(id: startup.id ?? 0)) ?? [] }
                    }
                }
            }
        }.frame(maxWidth: .infinity, alignment: .leading).reconCard()
    }

    private func generateWriteup() async {
        generatingWriteup = true
        if let res = try? await ReconAPI.shared.generateStartupWriteup(id: startup.id ?? 0), let md = res.markdown {
            detail?.writeupMarkdown = md
        }
        generatingWriteup = false
        onChanged()
    }

    private func researchContacts() async {
        researchingContacts = true
        plan = try? await ReconAPI.shared.researchStartupContacts(id: startup.id ?? 0)
        researchingContacts = false
    }
}

private struct StartupContactCard: View {
    let startupId: Int
    let target: ReachTarget
    let onAdded: () -> Void
    @State private var added = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(target.persona).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
            if let why = target.why, !why.isEmpty {
                Text(why).font(.caption).foregroundStyle(Theme.inkSoft)
            }
            if let opener = target.opener, !opener.isEmpty {
                Text(opener).font(.caption).italic().foregroundStyle(Theme.ink)
            }
            HStack(spacing: 10) {
                if let s = target.linkedinSearch, let url = URL(string: s) {
                    Link(destination: url) { Label("Find on LinkedIn", systemImage: "magnifyingglass") }
                        .buttonStyle(ReconButtonStyle(color: Theme.rust, soft: true))
                }
                Button { Task { await add() } } label: {
                    Label(added ? "Added" : "Add", systemImage: added ? "checkmark" : "person.badge.plus")
                }.buttonStyle(ReconButtonStyle(color: Theme.green, soft: true)).disabled(added)
            }
        }.padding(10).background(Theme.paper2.opacity(0.5), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private func add() async {
        let c = StartupContact(name: target.persona, role: target.persona, warmth: target.warmth,
                               notes: target.why)
        _ = try? await ReconAPI.shared.addStartupContact(startupId: startupId, c)
        added = true
        onAdded()
    }
}
