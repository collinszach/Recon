import SwiftUI

/// Drafts tailored cold outreach for a role, from Zach's real resume. Suggestion
/// only — he edits and sends.
struct OutreachView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss
    let role: Role

    @State private var result: Outreach?
    @State private var loading = true

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if loading {
                        VStack(spacing: 10) {
                            ProgressView()
                            Text("Drafting outreach for \(role.company ?? "this role")…")
                                .font(.caption).foregroundStyle(Theme.inkSoft)
                        }.frame(maxWidth: .infinity).padding(.top, 40)
                    } else if let err = result?.error {
                        ErrorBanner(message: err)
                    } else if let r = result {
                        if let s = r.subject, !s.isEmpty {
                            VStack(alignment: .leading, spacing: 6) {
                                HStack { label("Subject"); Spacer(); CopyButton(s) }
                                Text(s).font(.callout.weight(.medium)).foregroundStyle(Theme.ink)
                                    .textSelection(.enabled)
                            }.frame(maxWidth: .infinity, alignment: .leading).reconCard()
                        }
                        if let d = r.draft {
                            VStack(alignment: .leading, spacing: 6) {
                                HStack { label("Draft"); Spacer(); CopyButton(d) }
                                Text(d).font(.callout).foregroundStyle(Theme.ink).textSelection(.enabled)
                            }.frame(maxWidth: .infinity, alignment: .leading).reconCard()
                        }
                        Text("Edit before sending — it's a starting point, not a final message.")
                            .font(.caption2).foregroundStyle(Theme.inkSoft)
                    }
                }
                .padding(16)
            }
            .scrollContentBackground(.hidden)
            .background(Theme.paper.ignoresSafeArea())
            .navigationTitle("Draft outreach").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
        .task { result = await store.draftOutreach(roleId: role.id); loading = false }
    }

    private func label(_ t: String) -> some View {
        Text(t.uppercased()).font(.caption2.weight(.bold)).foregroundStyle(Theme.inkSoft)
    }
}

private struct CopyButton: View {
    let text: String
    init(_ t: String) { text = t }
    var body: some View {
        Button { UIPasteboard.general.string = text } label: {
            Image(systemName: "doc.on.doc").font(.caption2)
        }.tint(Theme.rust)
    }
}
