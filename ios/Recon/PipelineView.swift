import SwiftUI

/// Application pipeline grouped by stage, with inline stage moves.
struct PipelineView: View {
    @EnvironmentObject var store: Store

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let err = store.error { ErrorBanner(message: err) }

                if store.apps.isEmpty {
                    Text("No applications yet. Find an internship under Roles and tap Track to start a card here.")
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

struct AppCard: View {
    let app: AppItem
    @EnvironmentObject var store: Store

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(app.companyName ?? "—").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Spacer()
                if let f = app.fitScore {
                    Text("fit \(String(format: "%.1f", f))").font(.caption.weight(.semibold))
                        .foregroundStyle(Theme.fit(f))
                }
            }
            Text(app.roleTitle ?? "—").font(.callout).foregroundStyle(Theme.ink).lineLimit(2)
            if let na = app.nextAction, !na.isEmpty {
                Label(na, systemImage: "bell").font(.caption).foregroundStyle(Theme.rust)
            }
            HStack {
                if let u = app.roleUrl, let url = URL(string: u) {
                    Link("Posting", destination: url).font(.caption)
                }
                Spacer()
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
    }
}
