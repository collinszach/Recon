import SwiftUI

/// The dashboard: what was posted today, what needs action, what's in flight.
///
/// The ordering question this screen has to get right is "posted" vs "seen".
/// It used to group arrivals by `first_seen`, which meant a newly connected
/// board's entire back catalogue read as today's news — on 2026-09-21, 80
/// roles "arrived" and 7 had actually been posted that day. Everything here
/// keys off `posted_at`, and roles the board never dated get their own group
/// rather than padding the count.
struct TodayView: View {
    @EnvironmentObject var store: Store
    @State private var showUndated = false

    /// Posted earlier this week, grouped by posting day, newest day first.
    private var byDay: [(label: String, roles: [Role])] {
        let cal = Calendar.current
        let groups = Dictionary(grouping: store.postedThisWeek) { role -> Date in
            cal.startOfDay(for: role.postedDate ?? Date())
        }
        let fmt = DateFormatter(); fmt.dateFormat = "EEEE, MMM d"
        return groups.keys.sorted(by: >).map { day in
            let label = cal.isDateInYesterday(day) ? "Yesterday" : fmt.string(from: day)
            return (label, groups[day]?.sorted { ($0.company ?? "") < ($1.company ?? "") } ?? [])
        }
    }

    /// Actually applied — not "watching", which just means saved. The two used
    /// to be lumped together as "in flight", so the dashboard claimed 35
    /// applications when none had been sent.
    private var applied: [AppItem] {
        store.apps.filter { ["applied", "screen", "onsite", "offer"].contains($0.stage) }
    }
    /// Saved but not yet sent: the actual next thing to do.
    private var saved: [AppItem] {
        store.apps.filter { ["watching", "drafting"].contains($0.stage) }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let err = store.error { ErrorBanner(message: err) }

                HStack(spacing: 6) {
                    Text("Summer 2027 internships")
                        .font(.caption.weight(.semibold)).foregroundStyle(Theme.rust)
                        .textCase(.uppercase)
                    Spacer()
                    if let sync = store.lastSyncedText {
                        Text("synced \(sync)").font(.caption).foregroundStyle(Theme.inkSoft)
                    }
                }

                HStack(spacing: 10) {
                    Stat(num: "\(store.newToday.count)", label: "new today", color: Theme.gold)
                    Stat(num: "\(store.newWithin(days: 7).count)", label: "this week", color: Theme.rust)
                    Stat(num: "\(applied.count)", label: "applied", color: Theme.green)
                }

                // 1. New today — the reason to open the app. "New" is either
                // measure: the board dated it today, or it appeared on a board
                // that doesn't publish dates and wasn't there before. Plenty of
                // boards never date anything, and waiting for a date we'll never
                // get would mean never surfacing their postings at all.
                SectionHeader(title: "New today",
                              trailing: store.newToday.isEmpty ? nil : "\(store.newToday.count)")
                if store.newToday.isEmpty {
                    Text("Nothing new today yet. Recon scans hourly; most Summer 2027 reqs post Aug 2026–Jan 2027.")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                } else {
                    ForEach(store.newToday) { role in roleLink(role) }
                    if store.postedToday.count < store.newToday.count {
                        Text("\(store.newToday.count - store.postedToday.count) of these are from boards that don't publish posting dates — new means they weren't on the board before.")
                            .font(.caption).foregroundStyle(Theme.inkSoft)
                    }
                }

                // 2. Needs action, before the browsing sections.
                if store.totalNudgeCount > 0 { FollowUpsSection() }

                // 3. Earlier this week, by posting day.
                if !byDay.isEmpty {
                    SectionHeader(title: "Earlier this week",
                                  trailing: "\(store.postedThisWeek.count)")
                    ForEach(byDay.prefix(6), id: \.label) { day in
                        Text("\(day.label) · \(day.roles.count)")
                            .font(.caption.weight(.semibold)).foregroundStyle(Theme.inkSoft)
                            .textCase(.uppercase).padding(.top, 4)
                        ForEach(day.roles.prefix(6)) { role in roleLink(role) }
                        if day.roles.count > 6 {
                            Text("+ \(day.roles.count - 6) more in Roles")
                                .font(.caption).foregroundStyle(Theme.inkSoft)
                        }
                    }
                }

                // 4. Applications.
                if !applied.isEmpty {
                    SectionHeader(title: "Applied", trailing: "\(applied.count)")
                    ForEach(applied.prefix(5)) { app in appRow(app, tint: Theme.green) }
                    if applied.count > 5 {
                        Text("+ \(applied.count - 5) more in Pipeline")
                            .font(.caption).foregroundStyle(Theme.inkSoft)
                    }
                }

                SectionHeader(title: "Saved — not applied yet",
                              trailing: saved.isEmpty ? nil : "\(saved.count)")
                if saved.isEmpty {
                    Text("Nothing saved. Swipe right on a role — or tap Keep on one — and it lands here.")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                } else {
                    ForEach(saved.prefix(5)) { app in appRow(app, tint: Theme.gold) }
                    if saved.count > 5 {
                        Text("+ \(saved.count - 5) more in Pipeline")
                            .font(.caption).foregroundStyle(Theme.inkSoft)
                    }
                }

                // 5. Why the feed jumped: a board's back catalogue arriving is
                // explained here instead of silently swelling the counts above.
                if !store.recentBoards.isEmpty {
                    SectionHeader(title: "Boards connected", trailing: "\(store.recentBoards.count)")
                    ForEach(store.recentBoards) { b in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(b.company).font(.subheadline.weight(.semibold))
                                    .foregroundStyle(Theme.ink)
                                Text("\(b.rolesAdded) existing roles added\(b.ats.map { " · \($0)" } ?? "")")
                                    .font(.caption).foregroundStyle(Theme.inkSoft)
                            }
                            Spacer()
                        }
                        .reconCard()
                    }
                }

                // 6. Arrived with no posting date — visible, but never counted
                // as "today".
                if !store.undatedArrivals.isEmpty {
                    Button { withAnimation { showUndated.toggle() } } label: {
                        HStack {
                            Text("Older, date unknown · \(store.undatedArrivals.count)")
                                .font(.caption.weight(.semibold)).textCase(.uppercase)
                            Image(systemName: showUndated ? "chevron.up" : "chevron.down")
                                .font(.caption2)
                            Spacer()
                        }
                        .foregroundStyle(Theme.inkSoft)
                    }
                    .buttonStyle(.plain)
                    if showUndated {
                        ForEach(store.undatedArrivals.prefix(10)) { role in roleLink(role) }
                    }
                }
            }
            .padding(16)
        }
        .navigationDestination(for: Role.self) { RoleDetailView(role: $0, store: store) }
        .scrollContentBackground(.hidden)
    }

    private func roleLink(_ role: Role) -> some View {
        NavigationLink(value: role) { RoleRow(role: role, isNew: role.isNewToday) }
            .buttonStyle(.plain)
            .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                Button(role: .destructive) {
                    Task { await store.dismiss(role) }
                } label: { Label("Wipe", systemImage: "trash") }
            }
    }

    private func appRow(_ app: AppItem, tint: Color) -> some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(app.companyName ?? "—")
                    .font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Text(app.roleTitle ?? "—")
                    .font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(1)
            }
            Spacer()
            Pill(text: app.stage.capitalized, color: tint)
        }
        .reconCard()
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
