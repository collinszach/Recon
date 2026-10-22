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

    private var headerTitle: some View {
        Text("Summer 2027 internships")
            .font(.caption.weight(.semibold)).foregroundStyle(Theme.rust)
            .textCase(.uppercase)
            .accessibilityAddTraits(.isHeader)
    }
    @ViewBuilder private var syncLabel: some View {
        if let sync = store.lastSyncedText {
            Text("synced \(sync)").font(.caption).foregroundStyle(Theme.inkSoft)
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let err = store.error { ErrorBanner(message: err) }

                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 6) {
                        headerTitle
                        Spacer()
                        syncLabel
                    }
                    VStack(alignment: .leading, spacing: 4) { headerTitle; syncLabel }
                }

                // Is Recon working? Shown first and always — the mail check
                // was broken for a month and nothing on screen said so.
                StatusLine()

                AdaptiveRow {
                    Stat(num: "\(store.newToday.count)", label: "new today", color: Theme.gold)
                    Stat(num: "\(store.newWithin(days: 7).count)", label: "this week", color: Theme.rust)
                    // Same number as the Applications tab: everything ever sent, closed
                    // included — a rejection is still an application.
                    Stat(num: "\(store.appSummary?.applied ?? applied.count)", label: "applied", color: Theme.green)
                }

                // 1. Needs you: only what a human has to decide. Routine
                // confirmations and rejections are filed by Recon (see 3).
                let urgent = store.mailProposals
                if !urgent.isEmpty {
                    SectionHeader(title: "Needs you", trailing: "\(urgent.count)")
                    ForEach(urgent) { p in ProposalCard(proposal: p) }
                }
                if store.totalNudgeCount > 0 { FollowUpsSection() }
                if urgent.isEmpty && store.totalNudgeCount == 0 {
                    Label("Nothing needs you right now.", systemImage: "checkmark.circle")
                        .font(.subheadline).foregroundStyle(Theme.green).reconCard()
                }

                // 2. New today — the reason to open the app.
                SectionHeader(title: "New today",
                              trailing: store.newToday.isEmpty ? nil : "\(store.newToday.count)")
                if store.newToday.isEmpty {
                    Text("Nothing new yet today. Recon checks every hour; Jobs has the week.")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                } else {
                    ForEach(store.newToday.prefix(8)) { role in roleLink(role) }
                    if store.newToday.count > 8 {
                        Text("+ \(store.newToday.count - 8) more in Jobs")
                            .font(.caption).foregroundStyle(Theme.inkSoft)
                    }
                }

                // 3. What changed — including what Recon did on its own, each
                // with Undo. Automation you can't see is automation you can't trust.
                ActivitySection()
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

    private enum Item { case app(AppItem), contact(Contact) }

    /// Apps needing action and contacts needing follow-up, capped at 6 total.
    /// Apps open their detail screen — a follow-up you can't act on from the
    /// list is just a reminder of guilt.
    private var items: [(item: Item, label: String, sub: String, reason: String, urgency: Int)] {
        var out: [(Item, String, String, String, Int)] = []
        for app in store.apps where app.dueState != nil {
            let reason = app.dueState == .overdue ? "Action due" : "Past usual window"
            let urgency = app.dueState == .overdue ? 0 : 2
            out.append((.app(app), app.companyName ?? "—", app.roleTitle ?? "—", reason, urgency))
        }
        for c in store.followUpContacts {
            let reason = c.nextTouchDue ? "Touch due" : "No reply · 5d+"
            out.append((.contact(c), c.name ?? "—", c.company ?? "—", reason, 1))
        }
        return out.sorted { $0.4 < $1.4 }.prefix(6).map { $0 }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            SectionHeader(title: "Follow-ups",
                          trailing: "\(store.totalNudgeCount)")
            ForEach(Array(items.enumerated()), id: \.offset) { _, entry in
                switch entry.item {
                case .app(let app):
                    NavigationLink {
                        ApplicationDetailView(app: app).environmentObject(store)
                    } label: { row(entry, chevron: true) }
                    .buttonStyle(.plain)
                case .contact:
                    row(entry, chevron: false)
                }
            }
        }
    }

    private func row(_ entry: (item: Item, label: String, sub: String, reason: String, urgency: Int),
                     chevron: Bool) -> some View {
        HStack(spacing: 0) {
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .fill(entry.urgency == 0 ? Theme.rust : Theme.gold)
                .frame(width: 4)
                .padding(.vertical, 2)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(entry.label)
                        .font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                    Spacer()
                    Pill(text: entry.reason,
                         color: entry.urgency == 0 ? Theme.rust : Theme.gold,
                         filled: entry.urgency == 0)
                    if chevron {
                        Image(systemName: "chevron.right").font(.caption).foregroundStyle(Theme.inkSoft)
                    }
                }
                Text(entry.sub).font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(1)
            }
            .padding(.leading, 12)
        }
        .reconCard()
        .accessibilityElement(children: .combine)
    }
}

/// One reply, and what Recon thinks it means. The evidence is shown on purpose:
/// you're being asked to judge a guess, so the phrase that produced it is the
/// thing worth reading.
struct ProposalCard: View {
    @EnvironmentObject var store: Store
    let proposal: MailProposal

    private var tint: Color {
        switch proposal.kind {
        case "rejection":    return Theme.inkSoft
        case "offer":        return Theme.green
        case "screen":       return Theme.green
        case "info_request": return Theme.gold
        default:             return Theme.rust
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Pill(text: proposal.headline, color: tint, filled: true)
                Text(proposal.company ?? "—")
                    .font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Spacer()
                if let c = proposal.confidence, c != "high" {
                    Text(c).font(.caption2).foregroundStyle(Theme.inkSoft)
                }
            }
            if let role = proposal.roleTitle {
                Text(role).font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(1)
            }
            if let subject = proposal.subject {
                Text(subject).font(.callout).foregroundStyle(Theme.ink).lineLimit(2)
            }
            if let evidence = proposal.evidence {
                Text(evidence).font(.caption2).foregroundStyle(Theme.inkSoft).lineLimit(3)
            }
            HStack(spacing: 8) {
                if let label = proposal.actionLabel {
                    Button { Task { await store.acceptProposal(proposal) } } label: {
                        Text(label).font(.caption.weight(.semibold))
                            .padding(.horizontal, 12).padding(.vertical, 8)
                            .foregroundStyle(.white)
                            .background(tint, in: Capsule())
                    }
                } else {
                    // Acknowledgements and unreadable mail propose nothing —
                    // there is genuinely nothing to move, so don't invent a
                    // button that pretends otherwise.
                    Text("Nothing to change").font(.caption).foregroundStyle(Theme.inkSoft)
                }
                Button { Task { await store.dismissProposal(proposal) } } label: {
                    Text("Dismiss").font(.caption.weight(.medium))
                        .padding(.horizontal, 12).padding(.vertical, 8)
                        .foregroundStyle(Theme.inkSoft)
                        .background(Theme.card, in: Capsule())
                        .overlay(Capsule().stroke(Theme.hair))
                }
                Spacer()
            }
            .buttonStyle(.plain)
        }
        .reconCard()
    }
}

struct Stat: View {
    let num: String; let label: String; let color: Color
    @Environment(\.dynamicTypeSize) private var typeSize
    var body: some View {
        // At accessibility sizes the tiles stack (see AdaptiveRow), so number
        // and label sit side by side instead of the label breaking mid-word.
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 10))
            : AnyLayout(VStackLayout(alignment: .leading, spacing: 2))
        layout {
            Text(num).font(.system(.title, design: .serif).weight(.semibold)).foregroundStyle(color)
            Text(label).font(.caption2).foregroundStyle(Theme.inkSoft).textCase(.uppercase)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .reconCard()
        .accessibilityElement(children: .combine)
    }
}

/// A row of tiles that becomes a column at accessibility text sizes, where
/// three side by side leave each tile a few characters wide.
struct AdaptiveRow<Content: View>: View {
    var spacing: CGFloat = 10
    @ViewBuilder let content: Content
    @Environment(\.dynamicTypeSize) private var typeSize
    var body: some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: spacing))
            : AnyLayout(HStackLayout(alignment: .top, spacing: spacing))
        layout { content }
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
