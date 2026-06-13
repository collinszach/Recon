import SwiftUI

/// Per-role resume match analysis. Presented from a role's detail view.
struct TailorView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss
    let role: Role

    @State private var result: Tailoring?
    @State private var loading = true

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if loading {
                        VStack(spacing: 10) {
                            ProgressView()
                            Text("Matching your resume to this role…")
                                .font(.caption).foregroundStyle(Theme.inkSoft)
                        }.frame(maxWidth: .infinity).padding(.top, 40)
                    } else if let err = result?.error {
                        ErrorBanner(message: err)
                    } else if let t = result {
                        if let m = t.match_score {
                            HStack {
                                Text("Resume match").font(.headline).foregroundStyle(Theme.ink)
                                Spacer()
                                Text(String(format: "%.1f", m)).font(.title3.weight(.bold))
                                    .foregroundStyle(Theme.fit(m))
                            }.reconCard()
                        }
                        if let v = t.verdict { para("Verdict", v) }
                        list("Your strengths for this role", t.strengths, symbol: "plus.circle.fill", tint: Theme.green)
                        list("Gaps to address", t.gaps, symbol: "minus.circle.fill", tint: Theme.rust)
                        if let kw = t.keywords, !kw.isEmpty { keywords(kw) }
                        if let s = t.tailored_summary { copyBlock("Tailored summary", s) }
                        if let b = t.suggested_bullets, !b.isEmpty { bullets(b) }
                    }
                }
                .padding(16)
            }
            .scrollContentBackground(.hidden)
            .background(Theme.paper.ignoresSafeArea())
            .navigationTitle("Tailor résumé").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
        .task {
            result = await store.tailor(roleId: role.id)
            loading = false
        }
    }

    private func para(_ title: String, _ body: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            label(title); Text(body).font(.callout).foregroundStyle(Theme.ink)
        }.frame(maxWidth: .infinity, alignment: .leading).reconCard()
    }
    private func list(_ title: String, _ items: [String]?, symbol: String, tint: Color) -> some View {
        Group {
            if let items, !items.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    label(title)
                    ForEach(items, id: \.self) { i in
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: symbol).font(.caption).foregroundStyle(tint)
                            Text(i).font(.caption).foregroundStyle(Theme.ink)
                        }
                    }
                }.frame(maxWidth: .infinity, alignment: .leading).reconCard()
            }
        }
    }
    private func keywords(_ kw: [String]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            label("Keywords to surface")
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 90), spacing: 6)], alignment: .leading, spacing: 6) {
                ForEach(kw, id: \.self) { t in
                    Text(t).font(.caption2).foregroundStyle(Theme.ink)
                        .padding(.horizontal, 8).padding(.vertical, 4)
                        .background(Theme.gold.opacity(0.18), in: Capsule())
                }
            }
        }.frame(maxWidth: .infinity, alignment: .leading).reconCard()
    }
    private func copyBlock(_ title: String, _ text: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack { label(title); Spacer(); CopyButton(text) }
            Text(text).font(.callout).foregroundStyle(Theme.ink).textSelection(.enabled)
        }.frame(maxWidth: .infinity, alignment: .leading).reconCard()
    }
    private func bullets(_ items: [String]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            label("Suggested bullets")
            ForEach(items, id: \.self) { b in
                HStack(alignment: .top, spacing: 6) {
                    Text("•").foregroundStyle(Theme.rust)
                    Text(b).font(.caption).foregroundStyle(Theme.ink).textSelection(.enabled)
                    Spacer(minLength: 4)
                    CopyButton(b)
                }
            }
        }.frame(maxWidth: .infinity, alignment: .leading).reconCard()
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
