import SwiftUI

/// A small daily summary: the headline numbers, the top matches, and pipeline.
struct TodayView: View {
    @EnvironmentObject var store: Store

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let err = store.error { ErrorBanner(message: err) }

                // headline
                SectionHeader(title: "Recruiting today",
                              eyebrow: "Summer 2027 + full-time",
                              trailing: store.brief?.date)

                // stat row
                HStack(spacing: 10) {
                    Stat(num: "\(store.internFeed.count)", label: "internships", color: Theme.rust)
                    Stat(num: "\(store.fulltimeFeed.count)", label: "full-time", color: Theme.gold)
                    Stat(num: "\(store.apps.count)", label: "pipeline", color: Theme.green)
                }

                if store.totalNudgeCount > 0 {
                    FollowUpsSection()
                }

                SectionHeader(title: "Top matches",
                              trailing: store.newCount > 0 ? "\(store.newCount) new" : nil)
                if store.feed.isEmpty {
                    Text("No high-fit internships open yet. Most Summer 2027 reqs post Aug 2026–Jan 2027 — Recon scans daily and will surface them here.")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                } else {
                    ForEach(store.feed.prefix(5)) { role in
                        NavigationLink(value: role) { RoleRow(role: role, isNew: store.isNew(role)) }
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

/// Unified "things needing attention" section: overdue pipeline + contacts to nudge.
struct FollowUpsSection: View {
    @EnvironmentObject var store: Store

    /// Merge apps needing action and contacts needing follow-up, capped at 6 total.
    private var items: [(label: String, sub: String, reason: String, urgency: Int)] {
        var out: [(String, String, String, Int)] = []
        for app in store.apps where app.dueState != nil {
            let reason = app.dueState == .overdue ? "Action due" : "No update in 10d"
            let urgency = app.dueState == .overdue ? 0 : 2
            out.append((app.companyName ?? "—", app.roleTitle ?? "—", reason, urgency))
        }
        for c in store.followUpContacts {
            let reason = c.nextTouchDue ? "Touch due" : "No reply · 5d+"
            out.append((c.name ?? "—", c.company ?? "—", reason, 1))
        }
        return out.sorted { $0.3 < $1.3 }.prefix(6).map { $0 }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            SectionHeader(title: "Follow-ups",
                          trailing: "\(store.totalNudgeCount)")
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                HStack(spacing: 0) {
                    RoundedRectangle(cornerRadius: 2, style: .continuous)
                        .fill(item.urgency == 0 ? Theme.rust : Theme.gold)
                        .frame(width: 4)
                        .padding(.vertical, 2)
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Text(item.label)
                                .font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                            Spacer()
                            Pill(text: item.reason,
                                 color: item.urgency == 0 ? Theme.rust : Theme.gold,
                                 filled: item.urgency == 0)
                        }
                        Text(item.sub).font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(1)
                    }
                    .padding(.leading, 12)
                }
                .reconCard()
            }
        }
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
