import SwiftUI

/// Generate + save a one-page cover letter for a role.
struct CoverLetterView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss
    let role: Role
    @State private var doc: GenDoc?
    @State private var loading = true
    @State private var saved = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if loading {
                        VStack(spacing: 10) { ProgressView()
                            Text("Drafting a cover letter…").font(.caption).foregroundStyle(Theme.inkSoft)
                        }.frame(maxWidth: .infinity).padding(.top, 40)
                    } else if let err = doc?.error {
                        ErrorBanner(message: err)
                    } else if let d = doc {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text("Cover letter").font(.caption2.weight(.bold)).foregroundStyle(Theme.inkSoft)
                                Spacer()
                                Button { UIPasteboard.general.string = d.content }
                                    label: { Image(systemName: "doc.on.doc").font(.caption2) }.tint(Theme.rust)
                            }
                            Text(d.content ?? "").font(.callout).foregroundStyle(Theme.ink).textSelection(.enabled)
                        }.frame(maxWidth: .infinity, alignment: .leading).reconCard()

                        Button {
                            Task {
                                saved = await store.saveMaterial(Material(roleId: role.id, kind: "cover_letter",
                                    title: d.title ?? roleLabel, content: d.content))
                            }
                        } label: { Label(saved ? "Saved to vault" : "Save to vault",
                                         systemImage: saved ? "checkmark" : "tray.and.arrow.down") }
                            .buttonStyle(ReconButtonStyle(color: Theme.green, soft: true)).disabled(saved)

                        ExportPDFButton(title: d.title ?? roleLabel, body: d.content ?? "")
                    }
                }.padding(16)
            }
            .scrollContentBackground(.hidden).background(Theme.canvas.ignoresSafeArea())
            .navigationTitle("Cover letter").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
        .task { doc = await store.coverLetter(roleId: role.id); loading = false }
    }
    private var roleLabel: String { "\(role.company ?? "") — \(role.title)" }
}

/// Saved materials for a role: list + view + delete.
struct MaterialsCard: View {
    let role: Role
    var refresh: Int = 0
    @State private var materials: [Material] = []
    @State private var viewing: Material?

    var body: some View {
        Group {
            if !materials.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("SAVED MATERIALS").font(.caption2.weight(.bold)).foregroundStyle(Theme.inkSoft)
                    ForEach(materials) { m in
                        Button { viewing = m } label: {
                            HStack {
                                Pill(text: m.kindLabel, color: Theme.gold)
                                Text(m.title ?? m.kindLabel).font(.caption).foregroundStyle(Theme.ink).lineLimit(1)
                                Spacer()
                                Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.inkSoft)
                            }
                        }.buttonStyle(.plain)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading).reconCard()
            }
        }
        .task(id: refresh) { await reload() }
        .sheet(item: $viewing) { m in MaterialViewer(material: m) { await reload() } }
    }
    func reload() async { materials = (try? await ReconAPI.shared.materials(roleId: role.id)) ?? [] }
}

private struct MaterialViewer: View {
    let material: Material
    @Environment(\.dismiss) private var dismiss
    let onChange: () async -> Void

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(material.content ?? "").font(.callout).foregroundStyle(Theme.ink)
                        .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                    ExportPDFButton(title: material.title ?? material.kindLabel, body: material.content ?? "")
                }.padding(16)
            }
            .background(Theme.canvas.ignoresSafeArea())
            .navigationTitle(material.kindLabel).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { UIPasteboard.general.string = material.content } label: { Image(systemName: "doc.on.doc") }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button(role: .destructive) {
                        Task { if let id = material.id { try? await ReconAPI.shared.deleteMaterial(id: id) }
                            await onChange(); dismiss() }
                    } label: { Image(systemName: "trash") }
                }
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }
}
