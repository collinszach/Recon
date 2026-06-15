import SwiftUI

/// A small daily summary: the headline numbers, the top matches, and pipeline.
struct TodayView: View {
    @EnvironmentObject var store: Store

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if store.isOffline {
                    Label("Offline — showing last synced\(store.lastSyncedText.map { " \($0)" } ?? "")",
                          systemImage: "wifi.slash")
                        .font(.caption).foregroundStyle(Theme.inkSoft)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                        .background(Theme.gold.opacity(0.15), in: RoundedRectangle(cornerRadius: 10))
                }
                if let err = store.error { ErrorBanner(message: err) }

                // headline
                VStack(alignment: .leading, spacing: 4) {
                    Text("Summer 2027 internships + full-time PM")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft)
                    if let b = store.brief {
                        Text(b.date).font(.caption).foregroundStyle(Theme.inkSoft)
                    }
                }

                // stat row
                HStack(spacing: 10) {
                    Stat(num: "\(store.internFeed.count)", label: "internships", color: Theme.rust)
                    Stat(num: "\(store.fulltimeFeed.count)", label: "full-time", color: Theme.gold)
                    Stat(num: "\(store.apps.count)", label: "pipeline", color: Theme.green)
                }

                // top matches
                Text("Top matches").font(.headline).foregroundStyle(Theme.ink)
                if store.feed.isEmpty {
                    Text("No high-fit internships open yet. Most Summer 2027 reqs post Aug 2026–Jan 2027 — Recon scans daily and will surface them here.")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                } else {
                    ForEach(store.feed.prefix(5)) { role in
                        NavigationLink(value: role) { RoleRow(role: role) }
                            .buttonStyle(.plain)
                    }
                }
            }
            .padding(16)
        }
        .navigationDestination(for: Role.self) { RoleDetailView(role: $0) }
        .scrollContentBackground(.hidden)
    }
}

struct Stat: View {
    let num: String; let label: String; let color: Color
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(num).font(.system(.title, design: .serif).weight(.semibold)).foregroundStyle(color)
            Text(label).font(.caption2).foregroundStyle(Theme.inkSoft).textCase(.uppercase)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .reconCard()
    }
}

struct ErrorBanner: View {
    let message: String
    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(Theme.rust)
            Text(message).font(.footnote).foregroundStyle(Theme.ink)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.rust.opacity(0.10), in: RoundedRectangle(cornerRadius: 12))
    }
}
