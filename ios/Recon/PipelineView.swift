import SwiftUI

/// Applications: what you've sent, what you've saved, what's closed — and the
/// email that moves them. Watching bookmarks used to share one list with real
/// applications, so 25 saved postings buried the 20 that had been sent.
struct PipelineView: View {
    @EnvironmentObject var store: Store
    @State private var seg = Segment.active
    @State private var query = ""

    enum Segment: String, CaseIterable, Identifiable {
        case active = "Active", saved = "Saved", closed = "Closed", contacts = "Contacts"
        var id: String { rawValue }
    }

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $seg) {
                ForEach(Segment.allCases) { s in Text(label(s)).tag(s) }
            }
            .pickerStyle(.segmented).padding(.horizontal, 16).padding(.bottom, 8)

            if seg == .contacts { ContactsView() } else { applications }
        }
    }

    private func label(_ s: Segment) -> String {
        switch s {
        case .active:   return "Active \(store.apps.filter(\.isActive).count)"
        case .saved:    return "Saved \(store.apps.filter(\.isSaved).count)"
        case .closed:   return "Closed \(store.apps.filter { $0.stage == "closed" }.count)"
        case .contacts: return "Contacts"
        }
    }

    /// The segment's applications, filtered by the search box. Active sorts by
    /// stage (furthest along first), then most recently applied; the rest by
    /// most recent activity.
    private var items: [AppItem] {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        let base: [AppItem]
        switch seg {
        case .active:   base = store.apps.filter(\.isActive)
        case .saved:    base = store.apps.filter(\.isSaved)
        case .closed:   base = store.apps.filter { $0.stage == "closed" }
        case .contacts: base = []
        }
        let filtered = q.isEmpty ? base : base.filter {
            ($0.companyName ?? "").lowercased().contains(q) || ($0.roleTitle ?? "").lowercased().contains(q)
        }
        let rank = ["offer": 0, "onsite": 1, "screen": 2, "applied": 3]
        return filtered.sorted { a, b in
            if seg == .active, rank[a.stage] != rank[b.stage] {
                return (rank[a.stage] ?? 9) < (rank[b.stage] ?? 9)
            }
            let da = a.lastEmail?.date ?? a.appliedDate ?? .distantPast
            let db = b.lastEmail?.date ?? b.appliedDate ?? .distantPast
            return da > db
        }
    }

    private var applications: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let err = store.error { ErrorBanner(message: err) }
                if seg == .active {
                    SummaryStrip()
                    if !store.mailProposals.isEmpty { MailInbox() }
                }
                TextField("Search company or role", text: $query)
                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                    .padding(10).background(Theme.card, in: RoundedRectangle(cornerRadius: 10))
                if items.isEmpty {
                    Text(emptyText).font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                }
                if seg == .active {
                    let silent = items.filter(\.isSilent)
                    if !silent.isEmpty && query.isEmpty {
                        sectionHeader("No reply in 3+ weeks", count: silent.count, color: Theme.gold)
                        ForEach(silent) { AppCard(app: $0) }
                        sectionHeader("Everything active", count: items.count, color: Theme.ink)
                    }
                }
                ForEach(items) { AppCard(app: $0) }
            }
            .padding(16)
        }
        .scrollContentBackground(.hidden)
    }

    private var emptyText: String {
        switch seg {
        case .active: return query.isEmpty ? "Nothing sent yet. Applications appear here when you mark one applied, or accept a confirmation email." : "No active application matches."
        case .saved:  return "Nothing saved. Track a role under Roles to keep it here until you apply."
        default:      return "Nothing closed."
        }
    }

    private func sectionHeader(_ title: String, count: Int, color: Color) -> some View {
        HStack {
            Text(title).font(.headline).foregroundStyle(color)
            Text("\(count)").font(.caption.weight(.semibold)).foregroundStyle(Theme.inkSoft)
        }
    }
}

/// Applied · in progress · closed · response rate, from the server.
private struct SummaryStrip: View {
    @EnvironmentObject var store: Store
    var body: some View {
        let s = store.appSummary
        HStack(spacing: 10) {
            Stat(num: "\(s?.applied ?? store.apps.filter(\.isActive).count)", label: "applied", color: Theme.ink)
            Stat(num: "\(s?.interviewing ?? 0)", label: "interviewing", color: Theme.green)
            Stat(num: "\(s?.closed ?? 0)", label: "closed", color: Theme.rust)
            Stat(num: s?.responseRate.map { "\(Int(($0 * 100).rounded()))%" } ?? "—",
                 label: "heard back", color: Theme.gold)
        }
    }
}

/// Email Recon read and wants a yes/no on. Confirmations and rejections can go
/// in one tap; everything else is reviewed one at a time.
private struct MailInbox: View {
    @EnvironmentObject var store: Store
    @State private var expanded = false
    @State private var working = false
    @State private var result: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("\(store.mailProposals.count) update\(store.mailProposals.count == 1 ? "" : "s") from email",
                      systemImage: "envelope.badge")
                    .font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Spacer()
                Button(expanded ? "Hide" : "Review") { withAnimation { expanded.toggle() } }
                    .font(.caption.weight(.semibold)).foregroundStyle(Theme.rust)
            }
            let bulk = store.bulkProposals
            if !bulk.isEmpty {
                let rejections = bulk.filter { $0.kind == "rejection" }.count
                Button {
                    working = true
                    Task { result = await store.acceptAllProposals(); working = false }
                } label: {
                    HStack {
                        if working { ProgressView().tint(.white) }
                        Text("Accept \(bulk.count - rejections) confirmation\(bulk.count - rejections == 1 ? "" : "s") + \(rejections) rejection\(rejections == 1 ? "" : "s")")
                            .font(.caption.weight(.semibold))
                    }
                    .padding(.horizontal, 12).padding(.vertical, 8).frame(maxWidth: .infinity)
                    .foregroundStyle(.white).background(Theme.rust, in: Capsule())
                }
                .disabled(working)
            }
            if let r = result {
                Text(r).font(.caption).foregroundStyle(Theme.green)
            }
            if expanded {
                ForEach(store.mailProposals) { ProposalCard(proposal: $0) }
            }
        }
        .reconCard()
    }
}

/// Networking contacts — add/edit warm connections per company.
struct ContactsView: View {
    @EnvironmentObject var store: Store
    @State private var editing: Contact?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Button { editing = Contact() } label: {
                    Label("Add contact", systemImage: "person.badge.plus").frame(maxWidth: .infinity)
                }.buttonStyle(.borderedProminent).tint(Theme.rust)

                if store.contacts.isEmpty {
                    Text("No contacts yet. Add recruiters, hiring managers, and warm intros here.")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                }
                ForEach(sorted) { c in
                    Button { editing = c } label: { contactCard(c) }.buttonStyle(.plain)
                }
            }
            .padding(16)
        }
        .scrollContentBackground(.hidden)
        .task { if store.contacts.isEmpty { await store.loadContacts() } }
        .sheet(item: $editing) { ContactEditor(contact: $0) }
    }

    /// Needs-attention first (to-reach or next-touch due), then by name.
    private var sorted: [Contact] {
        store.contacts.sorted { a, b in
            func score(_ c: Contact) -> Int {
                if c.nextTouchDue { return 0 }
                if (c.status ?? "to_reach") == "to_reach" { return 1 }
                return 2
            }
            let sa = score(a), sb = score(b)
            return sa != sb ? sa < sb : (a.name ?? "") < (b.name ?? "")
        }
    }

    private func statusColor(_ s: String?) -> Color {
        switch s { case "met": return Theme.green; case "replied": return Theme.rust
                   case "sent": return Theme.gold; default: return Theme.inkSoft }
    }

    private func contactCard(_ c: Contact) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Text(c.name ?? "—").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Pill(text: c.statusLabel, color: statusColor(c.status))
                Spacer()
                if c.nextTouchDue {
                    Pill(text: "Reach out", color: Theme.rust, filled: true)
                } else if let w = c.warmth, !w.isEmpty {
                    Text(w).font(.caption2.weight(.medium)).foregroundStyle(Theme.gold)
                }
            }
            if let r = c.role, !r.isEmpty { Text(r).font(.caption).foregroundStyle(Theme.inkSoft) }
            else if let co = c.company, !co.isEmpty { Text(co).font(.caption).foregroundStyle(Theme.inkSoft) }
            HStack(spacing: 12) {
                if let e = c.email, !e.isEmpty, let url = URL(string: "mailto:\(e)") {
                    Link("Email", destination: url).font(.caption2)
                }
                if let l = c.linkedin, !l.isEmpty, let url = URL(string: l.hasPrefix("http") ? l : "https://\(l)") {
                    Link("LinkedIn", destination: url).font(.caption2)
                }
            }
            if let n = c.notes, !n.isEmpty { Text(n).font(.caption2).foregroundStyle(Theme.inkSoft).lineLimit(2) }
        }
        .reconCard()
    }
}

struct ContactEditor: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss
    @State var contact: Contact
    @State private var hasNext: Bool
    @State private var nextDate: Date

    init(contact: Contact) {
        _contact = State(initialValue: contact)
        let d = contact.nextTouch.flatMap { DateFormatter.ymd.date(from: String($0.prefix(10))) }
        _hasNext = State(initialValue: d != nil)
        _nextDate = State(initialValue: d ?? Date())
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Who") {
                    TextField("Name", text: bind(\.name))
                    TextField("Company", text: bind(\.company))
                    TextField("Role / title", text: bind(\.role))
                    TextField("Warmth (cold / warm / strong)", text: bind(\.warmth))
                }
                Section("Outreach") {
                    Picker("Status", selection: bind(\.status, default: "to_reach")) {
                        ForEach(Contact.statuses, id: \.self) { s in
                            Text(label(s)).tag(s)
                        }
                    }
                    Toggle("Next touch reminder", isOn: $hasNext)
                    if hasNext { DatePicker("Reach out by", selection: $nextDate, displayedComponents: .date) }
                }
                Section("Reach") {
                    TextField("Email", text: bind(\.email)).textInputAutocapitalization(.never).keyboardType(.emailAddress)
                    TextField("LinkedIn URL", text: bind(\.linkedin)).textInputAutocapitalization(.never)
                }
                if let o = contact.lastOutreach, !o.isEmpty {
                    Section("Last outreach") { Text(o).font(.footnote).foregroundStyle(.secondary) }
                }
                Section("Notes") { TextEditor(text: bind(\.notes)).frame(minHeight: 100) }
            }
            .navigationTitle(contact.id == nil ? "Add contact" : "Edit contact")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        contact.nextTouch = hasNext ? DateFormatter.ymd.string(from: nextDate) : nil
                        Task { await store.saveContact(contact); dismiss() }
                    }
                }
            }
        }
    }
    private func bind(_ kp: WritableKeyPath<Contact, String?>) -> Binding<String> {
        Binding(get: { contact[keyPath: kp] ?? "" }, set: { contact[keyPath: kp] = $0 })
    }
    private func bind(_ kp: WritableKeyPath<Contact, String?>, default def: String) -> Binding<String> {
        Binding(get: { contact[keyPath: kp] ?? def }, set: { contact[keyPath: kp] = $0 })
    }
    private func label(_ s: String) -> String {
        ["to_reach": "To reach", "sent": "Reached out", "replied": "Replied", "met": "Met"][s] ?? s
    }
}

struct AppCard: View {
    let app: AppItem
    @EnvironmentObject var store: Store

    var body: some View {
        NavigationLink {
            ApplicationDetailView(app: app)
        } label: {
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 8) {
                    Text(app.companyName ?? "—").font(.subheadline.weight(.semibold))
                        .foregroundStyle(Theme.ink)
                    StagePill(stage: app.stage)
                    dueBadge
                    Spacer()
                    Image(systemName: "chevron.right").font(.caption).foregroundStyle(Theme.inkSoft)
                }
                Text(app.roleTitle ?? "—").font(.callout).foregroundStyle(Theme.ink)
                    .lineLimit(2).multilineTextAlignment(.leading)
                HStack(spacing: 10) {
                    if let d = app.appliedDate {
                        Text("Applied \(d.formatted(.dateTime.month(.abbreviated).day()))"
                             + (app.daysSinceApplied.map { " · \($0)d" } ?? ""))
                    }
                    if let e = app.lastEmail, e.kind != "ack" || app.appliedDate == nil {
                        Text("\(e.label)\(e.date.map { " \($0.formatted(.dateTime.month(.abbreviated).day()))" } ?? "")")
                            .foregroundStyle(e.kind == "rejection" ? Theme.rust : Theme.green)
                    }
                }
                .font(.caption).foregroundStyle(Theme.inkSoft)
                if let na = app.nextAction, !na.isEmpty {
                    Label("\(na)\(app.nextActionDue.map { " · due \($0.prefix(10))" } ?? "")", systemImage: "bell")
                        .font(.caption).foregroundStyle(Theme.rust)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .reconCard()
        }
        .buttonStyle(.plain)
        .contextMenu {
            ForEach(Stage.allCases) { s in
                Button("Move to \(s.label)") { Task { await store.move(app, to: s) } }
            }
        }
    }

    @ViewBuilder private var dueBadge: some View {
        if app.isSilent {
            badge("NO REPLY", Theme.gold)
        } else {
            switch app.dueState {
            case .overdue: badge("DUE", Theme.rust)
            case .stale, nil: EmptyView()
            }
        }
    }
    private func badge(_ t: String, _ c: Color) -> some View {
        Text(t).font(.caption2.weight(.bold)).foregroundStyle(.white)
            .padding(.horizontal, 6).padding(.vertical, 2).background(c, in: Capsule())
    }
}

struct StagePill: View {
    let stage: String
    var body: some View {
        Text(stage.capitalized).font(.caption2.weight(.semibold))
            .padding(.horizontal, 6).padding(.vertical, 2)
            .foregroundStyle(color).overlay(Capsule().stroke(color.opacity(0.6), lineWidth: 1))
    }
    private var color: Color {
        switch stage {
        case "screen", "onsite", "offer": return Theme.green
        case "closed": return Theme.inkSoft
        case "applied": return Theme.ink
        default: return Theme.gold
        }
    }
}

/// One application: where it stands, what happened, and the controls.
struct ApplicationDetailView: View {
    let app: AppItem
    @EnvironmentObject var store: Store
    @State private var items: [TimelineItem] = []
    @State private var loaded = false
    @State private var showEdit = false

    private var current: AppItem { store.apps.first { $0.id == app.id } ?? app }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 6) {
                    HStack { StagePill(stage: current.stage); Spacer() }
                    Text(current.roleTitle ?? "—").font(.title3.weight(.semibold)).foregroundStyle(Theme.ink)
                    if let d = current.appliedDate {
                        Text("Applied \(d.formatted(date: .abbreviated, time: .omitted))"
                             + (current.daysSinceApplied.map { " · \($0) days ago" } ?? ""))
                            .font(.caption).foregroundStyle(Theme.inkSoft)
                    }
                    HStack(spacing: 14) {
                        if let u = current.roleUrl, let url = URL(string: u) {
                            Link(destination: url) { Label("Posting", systemImage: "safari") }
                        }
                        Menu {
                            ForEach(Stage.allCases) { s in
                                Button(s.label) { Task { await store.move(current, to: s); await load() } }
                            }
                        } label: { Label("Move", systemImage: "arrow.left.arrow.right") }
                        Button { showEdit = true } label: { Label("Edit", systemImage: "slider.horizontal.3") }
                    }
                    .font(.caption.weight(.semibold)).foregroundStyle(Theme.rust)
                    if let n = current.notes, !n.isEmpty {
                        Text(n).font(.callout).foregroundStyle(Theme.ink).padding(.top, 4)
                    }
                }
                .reconCard()

                Text("History").font(.headline).foregroundStyle(Theme.ink)
                if loaded && items.isEmpty {
                    Text("Nothing recorded yet.").font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                }
                ForEach(items) { TimelineRow(item: $0) }
            }
            .padding(16)
        }
        .background(Theme.canvas.ignoresSafeArea())
        .navigationTitle(current.companyName ?? "Application").navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .sheet(isPresented: $showEdit, onDismiss: { Task { await load() } }) {
            AppEditor(app: current).environmentObject(store)
        }
    }

    private func load() async {
        items = await store.timeline(for: app)
        loaded = true
    }
}

private struct TimelineRow: View {
    let item: TimelineItem
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: item.type == "email" ? "envelope" : "arrow.right.circle")
                .foregroundStyle(item.kind == "rejection" ? Theme.rust : Theme.inkSoft)
                .frame(width: 18)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                if let detail { Text(detail).font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(3) }
                if let d = Role.parseDate(item.at) {
                    Text(d.formatted(date: .abbreviated, time: .shortened))
                        .font(.caption2).foregroundStyle(Theme.inkSoft)
                }
            }
            Spacer(minLength: 0)
        }
        .reconCard()
    }
    private var title: String {
        if item.type == "email" { return item.subject ?? "Email" }
        switch (item.fromStage, item.toStage) {
        case (nil, let to?): return "Added as \(to.capitalized)"
        case (let from?, let to?): return "\(from.capitalized) → \(to.capitalized)"
        default: return "Updated"
        }
    }
    private var detail: String? {
        item.type == "email" ? item.snippet?.decodingHTMLEntities : item.note
    }
}

private struct AppEditor: View {
    let app: AppItem
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss

    @State private var stage: String
    @State private var nextAction: String
    @State private var hasDue: Bool
    @State private var due: Date
    @State private var notes: String
    @State private var outcome: String

    init(app: AppItem) {
        self.app = app
        _stage = State(initialValue: app.stage)
        _nextAction = State(initialValue: app.nextAction ?? "")
        _hasDue = State(initialValue: app.dueDateValue != nil)
        _due = State(initialValue: app.dueDateValue ?? Date())
        _notes = State(initialValue: app.notes ?? "")
        _outcome = State(initialValue: app.outcome ?? "")
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Stage") {
                    Picker("Stage", selection: $stage) {
                        ForEach(Stage.allCases) { Text($0.label).tag($0.rawValue) }
                    }
                }
                Section("Next action") {
                    TextField("e.g. Follow up with recruiter", text: $nextAction)
                    Toggle("Has due date", isOn: $hasDue)
                    if hasDue { DatePicker("Due", selection: $due, displayedComponents: .date) }
                }
                Section {
                    NavigationLink {
                        ScrollView { InterviewsCard(appId: app.id).padding(16) }
                            .background(Theme.canvas.ignoresSafeArea())
                            .navigationTitle("Interviews").navigationBarTitleDisplayMode(.inline)
                    } label: { Label("Interview rounds", systemImage: "person.2.wave.2") }
                }
                Section("Notes") { TextEditor(text: $notes).frame(minHeight: 80) }
                if stage == "closed" {
                    Section("Outcome") { TextField("won / lost / withdrawn", text: $outcome) }
                }
            }
            .navigationTitle(app.companyName ?? "Application").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await save(); dismiss() } }
                }
            }
        }
    }

    private func save() async {
        let body = ReconAPI.AppUpdate(
            stage: stage == app.stage ? nil : stage,
            next_action: nextAction.isEmpty ? nil : nextAction,
            next_action_due: hasDue ? DateFormatter.ymd.string(from: due) : nil,
            notes: notes.isEmpty ? nil : notes,
            outcome: outcome.isEmpty ? nil : outcome)
        await store.updateApp(app, body)
    }
}
