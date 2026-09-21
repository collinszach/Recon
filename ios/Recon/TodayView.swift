import SwiftUI

/// The dashboard: what arrived, what needs action, what's in flight.
///
/// Was a scored digest — headline stats, "Top matches" by fit. With the scorer
/// off (2026-09-21) fit is gone, so the questions this answers are the tracker's:
/// what's new since I last looked, what am I late on, and where do my
/// applications stand.
struct TodayView: View {
    @EnvironmentObject var store: Store

    /// New arrivals grouped by the day Recon first saw them, newest day first.
    private var byDay: [(label: String, roles: [Role])] {
        let cal = Calendar.current
        let groups = Dictionary(grouping: store.newThisWeek) { role -> Date in
            cal.startOfDay(for: role.firstSeenDate ?? Date())
        }
        let fmt = DateFormatter(); fmt.dateFormat = "EEEE, MMM d"
        return groups.keys.sorted(by: >).map { day in
            let label = cal.isDateInToday(day) ? "Today"
                      : cal.isDateInYesterday(day) ? "Yesterday"
                      : fmt.string(from: day)
            return (label, groups[day]?.sorted { ($0.company ?? "") < ($1.company ?? "") } ?? [])
        }
    }

    private var inFlight: [AppItem] {
        store.apps.filter { $0.stage != "closed" }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let err = store.error { ErrorBanner(message: err) }

                SectionHeader(title: "Recon",
                              eyebrow: "Summer 2027 internships",
                              trailing: store.lastSyncedText.map { "synced \($0)" })

                HStack(spacing: 10) {
                    Stat(num: "\(store.newThisWeek.count)", label: "new this week", color: Theme.gold)
                    Stat(num: "\(inFlight.count)", label: "in flight", color: Theme.green)
                    Stat(num: "\(store.dismissedCount)", label: "wiped", color: Theme.inkSoft)
                }

                if store.totalNudgeCount > 0 {
                    FollowUpsSection()
                }

                // Applications, the half of the tracker that isn't intake.
                SectionHeader(title: "Applied",
                              trailing: inFlight.isEmpty ? nil : "\(inFlight.count)")
                if inFlight.isEmpty {
                    Text("Nothing in flight. Swipe right on a role — or tap Track on one — and it lands here.")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                } else {
                    ForEach(inFlight.prefix(6)) { app in
                        HStack(spacing: 10) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(app.companyName ?? "—")
                                    .font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                                Text(app.roleTitle ?? "—")
                                    .font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(1)
                            }
                            Spacer()
                            Pill(text: app.stage.capitalized, color: Theme.green)
                        }
                        .reconCard()
                    }
                    if inFlight.count > 6 {
                        Text("+ \(inFlight.count - 6) more in Pipeline")
                            .font(.caption).foregroundStyle(Theme.inkSoft)
                    }
                }

                // New arrivals, grouped by day — the "did the scan find anything"
                // question, which the old fit-sorted list couldn't answer because
                // a day's arrivals never cracked the top 5.
                SectionHeader(title: "New this week",
                              trailing: store.newThisWeek.isEmpty ? nil : "\(store.newThisWeek.count)")
                if store.newThisWeek.isEmpty {
                    Text("Nothing new in the last 7 days. Most Summer 2027 reqs post Aug 2026–Jan 2027 — Recon scans hourly.")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                } else {
                    ForEach(byDay.prefix(4), id: \.label) { day in
                        Text("\(day.label) · \(day.roles.count)")
                            .font(.caption.weight(.semibold)).foregroundStyle(Theme.inkSoft)
                            .textCase(.uppercase).padding(.top, 4)
                        ForEach(day.roles.prefix(8)) { role in
                            NavigationLink(value: role) {
                                RoleRow(role: role, isNew: role.firstSeenIsToday)
                            }
                            .buttonStyle(.plain)
                            .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                Button(role: .destructive) {
                                    Task { await store.dismiss(role) }
                                } label: { Label("Wipe", systemImage: "trash") }
                            }
                        }
                        if day.roles.count > 8 {
                            Text("+ \(day.roles.count - 8) more in Roles")
                                .font(.caption).foregroundStyle(Theme.inkSoft)
                        }
                    }
                }
            }
            .padding(16)
        }
        .navigationDestination(for: Role.self) { RoleDetailView(role: $0, store: store) }
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
