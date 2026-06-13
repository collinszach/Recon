import SwiftUI

/// View + edit the master resume that drives per-role tailoring.
struct ResumeView: View {
    @EnvironmentObject var store: Store
    @State private var editProfile = false
    @State private var editExp: Experience?
    @State private var addKind: String?

    private let kinds: [(String, String)] = [("work", "Experience"),
                                              ("project", "Projects"),
                                              ("leadership", "Leadership")]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let err = store.error { ErrorBanner(message: err) }

                if let r = store.resume {
                    profileCard(r.profile)
                    ForEach(kinds, id: \.0) { kind, label in
                        let items = r.experiences.filter { $0.kind == kind }
                        HStack {
                            Text(label).font(.headline).foregroundStyle(Theme.ink)
                            Spacer()
                            Button { addKind = kind } label: { Image(systemName: "plus.circle") }
                                .tint(Theme.rust)
                        }
                        if items.isEmpty {
                            Text("None yet").font(.caption).foregroundStyle(Theme.inkSoft)
                        }
                        ForEach(items) { e in
                            Button { editExp = e } label: { expRow(e) }.buttonStyle(.plain)
                        }
                    }
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 40)
                }
            }
            .padding(16)
        }
        .scrollContentBackground(.hidden)
        .task { if store.resume == nil { await store.loadResume() } }
        .sheet(isPresented: $editProfile) {
            if let r = store.resume { ProfileEditor(profile: r.profile) }
        }
        .sheet(item: $editExp) { ExperienceEditor(exp: $0) }
        .sheet(item: Binding(get: { addKind.map { Experience(id: nil, kind: $0) } },
                             set: { _ in addKind = nil })) { ExperienceEditor(exp: $0) }
    }

    private func profileCard(_ p: ResumeProfile) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(p.full_name ?? "Your name").font(.title3.weight(.semibold)).foregroundStyle(Theme.ink)
                    if let h = p.headline { Text(h).font(.subheadline).foregroundStyle(Theme.rust) }
                    if let l = p.location { Text(l).font(.caption).foregroundStyle(Theme.inkSoft) }
                }
                Spacer()
                Button("Edit") { editProfile = true }.font(.subheadline).tint(Theme.rust)
            }
            if let s = p.summary, !s.isEmpty {
                Text(s).font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(4).padding(.top, 2)
            }
            if let sk = p.skills, !sk.isEmpty {
                Text(sk).font(.caption2).foregroundStyle(Theme.inkSoft).lineLimit(3).padding(.top, 2)
            }
        }
        .reconCard()
    }

    private func expRow(_ e: Experience) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(e.company ?? "—").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Spacer()
                Text(e.dateRange).font(.caption2).foregroundStyle(Theme.inkSoft)
            }
            if let t = e.title { Text(t).font(.caption).foregroundStyle(Theme.inkSoft) }
            if let b = e.bullets?.split(separator: "\n").first {
                Text(b).font(.caption2).foregroundStyle(Theme.inkSoft).lineLimit(2)
            }
        }
        .reconCard()
    }
}

private struct ProfileEditor: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss
    @State var profile: ResumeProfile

    var body: some View {
        NavigationStack {
            Form {
                Section("Header") {
                    TextField("Full name", text: bind(\.full_name))
                    TextField("Headline", text: bind(\.headline))
                    TextField("Location", text: bind(\.location))
                    TextField("Links", text: bind(\.links))
                }
                Section("Summary") { TextEditor(text: bind(\.summary)).frame(minHeight: 120) }
                Section("Skills") { TextEditor(text: bind(\.skills)).frame(minHeight: 100) }
                Section("Education") { TextEditor(text: bind(\.education)).frame(minHeight: 80) }
            }
            .navigationTitle("Edit profile").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await store.saveProfile(profile); dismiss() } }
                }
            }
        }
    }
    private func bind(_ kp: WritableKeyPath<ResumeProfile, String?>) -> Binding<String> {
        Binding(get: { profile[keyPath: kp] ?? "" }, set: { profile[keyPath: kp] = $0 })
    }
}

private struct ExperienceEditor: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss
    @State var exp: Experience

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker("Type", selection: bind(\.kind, "work")) {
                        Text("Experience").tag("work"); Text("Project").tag("project"); Text("Leadership").tag("leadership")
                    }
                }
                Section("Role") {
                    TextField("Company / project", text: bindOpt(\.company))
                    TextField("Title", text: bindOpt(\.title))
                    TextField("Location", text: bindOpt(\.location))
                    TextField("Start (e.g. Aug 2023)", text: bindOpt(\.start_date))
                    TextField("End (or Present)", text: bindOpt(\.end_date))
                }
                Section("Bullets (one per line)") {
                    TextEditor(text: bindOpt(\.bullets)).frame(minHeight: 160)
                }
                if exp.id != nil {
                    Section {
                        Button("Delete", role: .destructive) {
                            Task { await store.deleteExperience(exp); dismiss() }
                        }
                    }
                }
            }
            .navigationTitle(exp.id == nil ? "Add" : "Edit").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await store.saveExperience(exp); dismiss() } }
                }
            }
        }
    }
    private func bindOpt(_ kp: WritableKeyPath<Experience, String?>) -> Binding<String> {
        Binding(get: { exp[keyPath: kp] ?? "" }, set: { exp[keyPath: kp] = $0 })
    }
    private func bind(_ kp: WritableKeyPath<Experience, String>, _ def: String) -> Binding<String> {
        Binding(get: { exp[keyPath: kp] }, set: { exp[keyPath: kp] = $0 })
    }
}
