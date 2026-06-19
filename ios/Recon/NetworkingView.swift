import SwiftUI

/// "Who to reach out to" — researched target personas + warm-path openers for a role.
struct NetworkingView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss
    let role: Role

    @State private var plan: NetworkingPlan?
    @State private var loading = true

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if loading {
                        loadingState
                    } else if let err = plan?.error {
                        ErrorBanner(message: err)
                    } else if let p = plan {
                        if let s = p.summary, !s.isEmpty { playCard(s) }
                        ForEach(Array((p.targets ?? []).enumerated()), id: \.element.id) { i, t in
                            TargetCard(role: role, target: t, rank: i + 1)
                                .environmentObject(store)
                        }
                        Text("Personas, not real names — Recon never invents people. Run the search to find the actual person, then reach out.")
                            .font(.caption2).foregroundStyle(Theme.inkSoft)
                            .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 4)
                    }
                }.padding(16)
            }
            .scrollContentBackground(.hidden).background(Theme.canvas.ignoresSafeArea())
            .navigationTitle("Who to reach out to").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
        .task { plan = await store.networking(roleId: role.id); loading = false }
    }

    private var loadingState: some View {
        VStack(spacing: 12) {
            ZStack {
                Circle().fill(Theme.rust.opacity(0.12)).frame(width: 64, height: 64)
                Image(systemName: "person.2.badge.gearshape").font(.title2).foregroundStyle(Theme.rust)
            }
            ProgressView()
            Text("Mapping the warmest way in…").font(.caption).foregroundStyle(Theme.inkSoft)
        }.frame(maxWidth: .infinity).padding(.top, 48)
    }

    private func playCard(_ s: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("THE PLAY", systemImage: "scope").font(.caption2.weight(.bold))
                .tracking(0.8).foregroundStyle(Theme.rust)
            Text(s).font(.callout.weight(.medium)).foregroundStyle(Theme.ink)
                .fixedSize(horizontal: false, vertical: true)
        }.frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
            .background(Theme.rust.opacity(0.08), in: RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Theme.corner, style: .continuous).stroke(Theme.rust.opacity(0.25), lineWidth: 1))
    }
}

/// A single target persona card: who, why, where to find, opener, and actions.
private struct TargetCard: View {
    @EnvironmentObject var store: Store
    let role: Role
    let target: ReachTarget
    let rank: Int
    @State private var added = false
    @State private var copied = false

    private var warmth: (label: String, color: Color, icon: String) {
        switch target.warmthTone {
        case .warm:   return ("Warm", Theme.green, "flame.fill")
        case .medium: return ("Medium", Theme.gold, "flame")
        case .cold:   return ("Cold", Theme.inkSoft, "snowflake")
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // header
            HStack(alignment: .top, spacing: 10) {
                Text("\(rank)").font(.caption.weight(.bold)).foregroundStyle(.white)
                    .frame(width: 22, height: 22).background(Theme.rust, in: Circle())
                Text(target.persona).font(.headline).foregroundStyle(Theme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 6)
                Label(warmth.label, systemImage: warmth.icon)
                    .font(.caption2.weight(.bold)).foregroundStyle(warmth.color)
                    .padding(.horizontal, 8).padding(.vertical, 4)
                    .background(warmth.color.opacity(0.14), in: Capsule())
            }

            if let why = target.why, !why.isEmpty {
                Text(why).font(.subheadline).foregroundStyle(Theme.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let hint = target.findHint, !hint.isEmpty {
                HStack(alignment: .top, spacing: 6) {
                    Image(systemName: "magnifyingglass").font(.caption).foregroundStyle(Theme.gold)
                    Text(hint).font(.caption).foregroundStyle(Theme.inkSoft)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            if let opener = target.opener, !opener.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text("OPENER").font(.caption2.weight(.bold)).tracking(0.6).foregroundStyle(Theme.inkSoft)
                        Spacer()
                        Button { UIPasteboard.general.string = opener; copied = true } label: {
                            Label(copied ? "Copied" : "Copy", systemImage: copied ? "checkmark" : "doc.on.doc")
                                .font(.caption2.weight(.semibold))
                        }.tint(Theme.rust)
                    }
                    Text(opener).font(.callout).italic().foregroundStyle(Theme.ink)
                        .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                }
                .padding(12)
                .background(Theme.paper2.opacity(0.6), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(Theme.hair, lineWidth: 0.75))
            }

            // actions
            HStack(spacing: 10) {
                if let s = target.linkedinSearch, let url = URL(string: s) {
                    Link(destination: url) {
                        Label("Find on LinkedIn", systemImage: "magnifyingglass")
                    }.buttonStyle(ReconButtonStyle(color: Theme.rust, soft: true))
                }
                Button { Task { await addContact() } } label: {
                    Label(added ? "Added" : "Add to CRM", systemImage: added ? "checkmark" : "person.badge.plus")
                }.buttonStyle(ReconButtonStyle(color: Theme.green, soft: true)).disabled(added)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading).reconCard()
    }

    private func addContact() async {
        var notes = target.why ?? ""
        if let o = target.opener { notes += (notes.isEmpty ? "" : "\n\nOpener: ") + o }
        let c = Contact(company: role.company, name: target.persona, role: target.persona,
                        warmth: target.warmth, status: "to_reach", notes: notes)
        await store.saveContact(c)
        added = true
    }
}
