import SwiftUI

/// Application pipeline + contacts, segmented.
struct PipelineView: View {
    @EnvironmentObject var store: Store
    @State private var seg = "apps"

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $seg) {
                Text("Applications (\(store.apps.count))").tag("apps")
                Text("Contacts (\(store.contacts.count))").tag("contacts")
            }
            .pickerStyle(.segmented).padding(.horizontal, 16).padding(.bottom, 8)

            if seg == "apps" { applications } else { ContactsView() }
        }
    }

    private var funnel: some View {
        let counts = store.stageCounts
        let order: [(String, String)] = [("watching","Watch"),("drafting","Draft"),
            ("applied","Applied"),("screen","Screen"),("onsite","Onsite"),("offer","Offer")]
        return VStack(alignment: .leading, spacing: 8) {
            if store.needActionCount > 0 {
                Label("\(store.needActionCount) need action", systemImage: "bell.badge")
                    .font(.caption.weight(.semibold)).foregroundStyle(Theme.rust)
            }
            HStack(spacing: 6) {
                ForEach(order, id: \.0) { key, label in
                    VStack(spacing: 2) {
                        Text("\(counts[key] ?? 0)").font(.headline).foregroundStyle(Theme.ink)
                        Text(label).font(.caption2).foregroundStyle(Theme.inkSoft)
                    }.frame(maxWidth: .infinity)
                }
            }
        }.reconCard()
    }

    private var applications: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let err = store.error { ErrorBanner(message: err) }
                if !store.apps.isEmpty { funnel }
                if store.apps.isEmpty {
                    Text("No applications yet. Find a role under Roles and tap Track to start a card here.")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                }
                ForEach(Stage.allCases) { stage in
                    let items = store.apps.filter { $0.stage == stage.rawValue }
                    if !items.isEmpty {
                        HStack {
                            Text(stage.label).font(.headline).foregroundStyle(Theme.ink)
                            Text("\(items.count)").font(.caption.weight(.semibold))
                                .foregroundStyle(Theme.inkSoft)
                        }
                        ForEach(items) { app in AppCard(app: app) }
                    }
                }
            }
            .padding(16)
        }
        .scrollContentBackground(.hidden)
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

private struct ContactEditor: View {
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
    @State private var showEdit = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(app.companyName ?? "—").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                dueBadge
                Spacer()
                if let f = app.fitScore {
                    Text("fit \(String(format: "%.1f", f))").font(.caption.weight(.semibold))
                        .foregroundStyle(Theme.fit(f))
                }
            }
            Text(app.roleTitle ?? "—").font(.callout).foregroundStyle(Theme.ink).lineLimit(2)
            if let na = app.nextAction, !na.isEmpty {
                Label("\(na)\(app.nextActionDue.map { " · due \($0.prefix(10))" } ?? "")", systemImage: "bell")
                    .font(.caption).foregroundStyle(Theme.rust)
            }
            HStack {
                if let u = app.roleUrl, let url = URL(string: u) {
                    Link("Posting", destination: url).font(.caption)
                }
                Spacer()
                Button { showEdit = true } label: {
                    Label("Edit", systemImage: "slider.horizontal.3")
                        .font(.caption.weight(.semibold)).foregroundStyle(Theme.rust)
                }
                Menu {
                    ForEach(Stage.allCases) { s in
                        Button(s.label) { Task { await store.move(app, to: s) } }
                    }
                } label: {
                    Label("Move", systemImage: "arrow.left.arrow.right")
                        .font(.caption.weight(.semibold)).foregroundStyle(Theme.rust)
                }
            }
        }
        .reconCard()
        .sheet(isPresented: $showEdit) { AppEditor(app: app).environmentObject(store) }
    }

    @ViewBuilder private var dueBadge: some View {
        switch app.dueState {
        case .overdue:
            Text("DUE").font(.caption2.weight(.bold)).foregroundStyle(.white)
                .padding(.horizontal, 6).padding(.vertical, 2).background(Theme.rust, in: Capsule())
        case .stale:
            Text("STALE").font(.caption2.weight(.bold)).foregroundStyle(.white)
                .padding(.horizontal, 6).padding(.vertical, 2).background(Theme.gold, in: Capsule())
        case nil: EmptyView()
        }
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
