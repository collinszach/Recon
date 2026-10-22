import SwiftUI

/// "Is Recon working?" in one line. Healthy is quiet; a failure becomes a
/// card that says what broke and how to fix it. Text and icon carry the
/// state, never color alone.
struct StatusLine: View {
    @EnvironmentObject var store: Store
    @State private var showDetail = false

    var body: some View {
        if let s = store.systemStatus {
            if s.isHealthy {
                Button { showDetail = true } label: {
                    Label {
                        Text("Mail checked \(ago(s.mail.at)) · Scan \(ago(s.scan.at))")
                    } icon: {
                        Image(systemName: "checkmark.circle.fill").foregroundStyle(Theme.green)
                    }
                    .font(.caption).foregroundStyle(Theme.inkSoft)
                    .frame(minHeight: 44, alignment: .leading)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Recon is working. Mail checked \(ago(s.mail.at)), scan \(ago(s.scan.at)).")
                .accessibilityHint("Shows details")
                .sheet(isPresented: $showDetail) { StatusDetail(status: s) }
            } else {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(problems(s), id: \.0) { name, job in
                        Label("\(name): \(headline(job))", systemImage: "exclamationmark.triangle.fill")
                            .font(.subheadline.weight(.semibold)).foregroundStyle(Theme.rust)
                        if let summary = job.summary {
                            Text(summary).font(.caption).foregroundStyle(Theme.ink).lineLimit(3)
                        }
                        if let fix = job.fix {
                            Text("Fix: \(fix)").font(.caption).foregroundStyle(Theme.inkSoft)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .reconCard()
                .accessibilityElement(children: .combine)
            }
        }
    }

    private func problems(_ s: SystemStatus) -> [(String, SystemStatus.Job)] {
        [("Mail", s.mail), ("Scan", s.scan)].filter { !$0.1.isHealthy }
    }
    private func headline(_ job: SystemStatus.Job) -> String {
        switch job.state {
        case "error": return "failing"
        case "stale": return "hasn't run in 3+ hours"
        case "never": return "hasn't run yet"
        default:      return job.state
        }
    }
}

func ago(_ iso: String?) -> String {
    guard let d = Role.parseDate(iso) else { return "never" }
    if Date().timeIntervalSince(d) < 60 { return "just now" }
    let f = RelativeDateTimeFormatter()
    f.unitsStyle = .short
    return f.localizedString(for: d, relativeTo: Date())
}

private struct StatusDetail: View {
    let status: SystemStatus
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            List {
                section("Mail", status.mail)
                section("Job scan", status.scan)
            }
            .navigationTitle("Recon status").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
        .presentationDetents([.medium])
    }
    private func section(_ title: String, _ job: SystemStatus.Job) -> some View {
        Section(title) {
            LabeledContent("State", value: job.state.capitalized)
            LabeledContent("Last run", value: ago(job.at))
            if let s = job.summary { Text(s).font(.callout) }
            if let f = job.fix { Text("Fix: \(f)").font(.callout).foregroundStyle(.secondary) }
        }
    }
}

/// Recent changes on Today, with the full log one tap away.
struct ActivitySection: View {
    @EnvironmentObject var store: Store
    var body: some View {
        if !store.activity.isEmpty {
            HStack {
                SectionHeader(title: "What changed", trailing: nil)
                Spacer()
                NavigationLink {
                    ActivityLog().environmentObject(store)
                } label: {
                    Text("See all").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.rust)
                        .frame(minHeight: 44)
                }
            }
            ForEach(store.activity.prefix(6)) { ActivityRow(item: $0) }
        }
    }
}

struct ActivityLog: View {
    @EnvironmentObject var store: Store
    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 10) {
                Text("Everything that changed, newest first. Recon's automatic filings can be undone.")
                    .font(.caption).foregroundStyle(Theme.inkSoft)
                ForEach(store.activity) { ActivityRow(item: $0) }
            }
            .padding(16)
        }
        .reconBackground()
        .navigationTitle("Activity").navigationBarTitleDisplayMode(.inline)
        .refreshable { await store.refresh() }
    }
}

struct ActivityRow: View {
    let item: ActivityItem
    @EnvironmentObject var store: Store
    @State private var working = false

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon).foregroundStyle(tint).frame(width: 22)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text(item.headline).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                    .strikethrough(item.undone)
                if let role = item.role {
                    Text(role).font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(2)
                }
                Text(byline).font(.caption2).foregroundStyle(Theme.inkSoft)
            }
            Spacer(minLength: 8)
            if item.undoable {
                Button {
                    working = true
                    Task { await store.undo(item); working = false }
                } label: {
                    if working { ProgressView() } else {
                        Text("Undo").font(.caption.weight(.semibold))
                            .padding(.horizontal, 12)
                            .frame(minWidth: 44, minHeight: 44)
                            .foregroundStyle(Theme.rust)
                            .overlay(Capsule().stroke(Theme.rust.opacity(0.6), lineWidth: 1))
                    }
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Undo: \(item.headline)")
            }
        }
        .reconCard()
        .accessibilityElement(children: .combine)
    }

    private var byline: String {
        let who = item.type == "scan" ? "Job scan" : (item.actor == "recon" ? "Filed by Recon from email" : "You")
        return "\(who) · \(ago(item.at))\(item.undone ? " · undone" : "")"
    }
    private var icon: String {
        if item.type == "scan" { return "dot.radiowaves.left.and.right" }
        if item.toStage == "closed" { return "xmark.circle" }
        return item.actor == "recon" ? "envelope.badge" : "person.crop.circle"
    }
    private var tint: Color {
        if item.toStage == "closed" { return Theme.rust }
        return item.actor == "recon" ? Theme.gold : Theme.inkSoft
    }
}
