import SwiftUI

/// AI interview prep for a role: likely questions, talking points, questions to ask.
struct InterviewPrepView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss
    let role: Role
    @State private var prep: InterviewPrep?
    @State private var loading = true

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if loading {
                        VStack(spacing: 10) {
                            ProgressView()
                            Text("Prepping you for \(role.company ?? "this interview")…")
                                .font(.caption).foregroundStyle(Theme.inkSoft)
                        }.frame(maxWidth: .infinity).padding(.top, 40)
                    } else if let err = prep?.error {
                        ErrorBanner(message: err)
                    } else if let p = prep {
                        list("Likely questions", p.likely_questions, "questionmark.circle.fill", Theme.rust)
                        list("Talking points (from your resume)", p.talking_points, "star.fill", Theme.green)
                        list("Questions to ask them", p.questions_to_ask, "hand.raised.fill", Theme.gold)
                        list("Watch-outs", p.watch_outs, "exclamationmark.triangle.fill", Theme.rust)
                    }
                }.padding(16)
            }
            .scrollContentBackground(.hidden).background(Theme.canvas.ignoresSafeArea())
            .navigationTitle("Interview prep").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
        .task { prep = await store.interviewPrep(roleId: role.id); loading = false }
    }

    private func list(_ title: String, _ items: [String]?, _ symbol: String, _ tint: Color) -> some View {
        Group {
            if let items, !items.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text(title.uppercased()).font(.caption2.weight(.bold)).foregroundStyle(Theme.inkSoft)
                    ForEach(items, id: \.self) { i in
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: symbol).font(.caption2).foregroundStyle(tint)
                            Text(i).font(.caption).foregroundStyle(Theme.ink).textSelection(.enabled)
                        }
                    }
                }.frame(maxWidth: .infinity, alignment: .leading).reconCard()
            }
        }
    }
}

/// Interview rounds for an application — list + add/edit. Used inside the app editor.
struct InterviewsCard: View {
    let appId: Int
    @State private var interviews: [Interview] = []
    @State private var editing: Interview?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Interviews").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Spacer()
                Button { editing = Interview(applicationId: appId) } label: { Image(systemName: "plus.circle") }
                    .tint(Theme.rust)
            }
            if interviews.isEmpty {
                Text("No rounds yet.").font(.caption).foregroundStyle(Theme.inkSoft)
            }
            ForEach(interviews) { iv in
                Button { editing = iv } label: { row(iv) }.buttonStyle(.plain)
            }
        }
        .reconCard()
        .task { await reload() }
        .sheet(item: $editing) { iv in
            InterviewEditor(appId: appId, interview: iv) { await reload() }
        }
    }

    private func reload() async {
        interviews = (try? await ReconAPI.shared.interviews(appId: appId)) ?? []
    }
    private func row(_ iv: Interview) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 1) {
                Text((iv.kind ?? "round").capitalized).font(.caption.weight(.semibold)).foregroundStyle(Theme.ink)
                if let i = iv.interviewer, !i.isEmpty { Text(i).font(.caption2).foregroundStyle(Theme.inkSoft) }
            }
            Spacer()
            if let d = iv.scheduledAt { Text(String(d.prefix(10))).font(.caption2).foregroundStyle(Theme.inkSoft) }
            if let o = iv.outcome, !o.isEmpty { Pill(text: o, color: o == "passed" ? Theme.green : Theme.inkSoft) }
        }.padding(.vertical, 2)
    }
}

private struct InterviewEditor: View {
    let appId: Int
    @Environment(\.dismiss) private var dismiss
    @State var interview: Interview
    let onSave: () async -> Void
    @State private var hasDate: Bool
    @State private var date: Date

    init(appId: Int, interview: Interview, onSave: @escaping () async -> Void) {
        self.appId = appId; self.onSave = onSave
        _interview = State(initialValue: interview)
        let d = interview.dateValue
        _hasDate = State(initialValue: d != nil); _date = State(initialValue: d ?? Date())
    }

    var body: some View {
        NavigationStack {
            Form {
                Picker("Type", selection: bind(\.kind, "recruiter")) {
                    ForEach(Interview.kinds, id: \.self) { Text($0.capitalized).tag($0) }
                }
                Toggle("Scheduled date", isOn: $hasDate)
                if hasDate { DatePicker("Date", selection: $date, displayedComponents: .date) }
                TextField("Interviewer", text: bind(\.interviewer))
                Picker("Outcome", selection: bind(\.outcome, "pending")) {
                    ForEach(["pending", "passed", "rejected"], id: \.self) { Text($0.capitalized).tag($0) }
                }
                Section("Notes") { TextEditor(text: bind(\.notes)).frame(minHeight: 90) }
                if interview.id != nil {
                    Button("Delete round", role: .destructive) {
                        Task { if let id = interview.id { try? await ReconAPI.shared.deleteInterview(id: id) }
                            await onSave(); dismiss() }
                    }
                }
            }
            .navigationTitle(interview.id == nil ? "Add round" : "Edit round")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        interview.scheduledAt = hasDate ? DateFormatter.ymd.string(from: date) : nil
                        Task {
                            if interview.id == nil {
                                _ = try? await ReconAPI.shared.addInterview(appId: appId, interview)
                            } else {
                                _ = try? await ReconAPI.shared.updateInterview(interview)
                            }
                            await onSave(); dismiss()
                        }
                    }
                }
            }
        }
    }
    private func bind(_ kp: WritableKeyPath<Interview, String?>, _ def: String) -> Binding<String> {
        Binding(get: { interview[keyPath: kp] ?? def }, set: { interview[keyPath: kp] = $0 })
    }
    private func bind(_ kp: WritableKeyPath<Interview, String?>) -> Binding<String> {
        Binding(get: { interview[keyPath: kp] ?? "" }, set: { interview[keyPath: kp] = $0 })
    }
}
