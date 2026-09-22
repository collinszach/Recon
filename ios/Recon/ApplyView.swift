import SwiftUI
import WebKit

/// The work queue: roles you've kept, with what it takes to actually submit
/// them, and the form itself one tap away.
///
/// The phone was previously triage-only — you'd find a role here and apply on
/// a laptop, which meant the two halves of the job search lived in different
/// places. This is the other half.
struct ApplyView: View {
    @EnvironmentObject var store: Store
    @State private var applying: Role?

    /// Kept roles that aren't applied yet. Saved is a promise to yourself;
    /// this is the list of promises outstanding.
    private var queue: [Role] {
        let appliedUrls = Set(store.apps
            .filter { !["watching", "drafting"].contains($0.stage) }
            .compactMap { $0.roleUrl })
        return store.feed
            .filter { store.interest(of: $0) == "up" && !appliedUrls.contains($0.url ?? "") }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let err = store.error { ErrorBanner(message: err) }

                if queue.isEmpty {
                    Text("Nothing queued. Keep a role — swipe right in triage, or tap Keep on one — and it lands here with everything you need to apply.")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft).reconCard()
                } else {
                    Text("\(queue.count) to apply")
                        .font(.caption.weight(.semibold)).foregroundStyle(Theme.inkSoft)
                        .textCase(.uppercase)
                    ForEach(queue) { role in
                        ApplyCard(role: role) { applying = role }
                    }
                }
            }
            .padding(16)
        }
        .scrollContentBackground(.hidden)
        .fullScreenCover(item: $applying) { role in
            ApplyFormView(role: role).environmentObject(store)
        }
    }
}

/// One queued role, and an honest read of what applying to it will involve.
private struct ApplyCard: View {
    @EnvironmentObject var store: Store
    let role: Role
    let onApply: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Text(role.company ?? "—")
                    .font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                if let term = role.termLabel { Pill(text: term, color: Theme.rust) }
                Spacer()
                Pill(text: role.portal.label, color: role.portal.tint)
            }
            Text(role.title).font(.callout).foregroundStyle(Theme.ink).lineLimit(2)
            if let loc = role.location, !loc.isEmpty {
                Label(loc, systemImage: "mappin.and.ellipse")
                    .font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(1)
            }

            // What's ready and what isn't, before you open the form rather
            // than after.
            HStack(spacing: 12) {
                readiness("JD", ok: (role.description?.count ?? 0) > 200)
                readiness("Résumé", ok: store.resumeOnFile)
                readiness("Profile", ok: store.autofillReady)
            }
            .font(.caption2)

            if role.portal.multiStep {
                Text("\(role.portal.label) is a multi-step form — Recon fills what it can see on each step, and you'll sign in yourself.")
                    .font(.caption2).foregroundStyle(Theme.inkSoft)
            }

            HStack(spacing: 8) {
                Button(action: onApply) {
                    Label("Apply", systemImage: "arrow.up.forward.app")
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, 14).padding(.vertical, 9)
                        .foregroundStyle(.white)
                        .background(Theme.rust, in: Capsule())
                }
                .disabled(role.url == nil)
                Button { Task { await store.dismiss(role) } } label: {
                    Text("Wipe").font(.caption.weight(.medium))
                        .padding(.horizontal, 12).padding(.vertical, 9)
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

    @ViewBuilder
    private func readiness(_ label: String, ok: Bool) -> some View {
        Label(label, systemImage: ok ? "checkmark.circle.fill" : "circle")
            .foregroundStyle(ok ? Theme.green : Theme.inkSoft)
    }
}

/// The posting itself, in-app, with a Fill button that injects the profile.
///
/// Same approach as the Chrome extension: write through the native value
/// setter and dispatch input/change, because every one of these portals is a
/// React app that discards a plain assignment on the next render.
struct ApplyFormView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss
    let role: Role

    @State private var isLoading = true
    @State private var loadError: String?
    @State private var reloadToken = 0
    @State private var report: String?
    @State private var filling = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if let url = role.url.flatMap(URL.init) {
                    AutofillWebView(url: url, isLoading: $isLoading,
                                    loadError: $loadError, reloadToken: reloadToken,
                                    fillRequest: $filling, profile: store.autofillProfile,
                                    onReport: { report = $0 })
                } else {
                    Text("This role has no application link.")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft)
                        .frame(maxHeight: .infinity)
                }
                if let report {
                    Text(report).font(.caption).foregroundStyle(Theme.inkSoft)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10).background(Theme.card)
                }
            }
            .navigationTitle(role.company ?? "Apply")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Close") { dismiss() }
                }
                ToolbarItem(placement: .bottomBar) {
                    Button {
                        filling = true
                    } label: { Label("Fill", systemImage: "wand.and.stars") }
                        .disabled(!store.autofillReady)
                }
                ToolbarItem(placement: .bottomBar) {
                    // Recon never submits a form. Marking it applied is a
                    // separate, deliberate act — the same rule the extension
                    // follows.
                    Button {
                        Task {
                            await store.setInterest(role, "up")
                            await store.track(role, stage: "applied")
                            dismiss()
                        }
                    } label: { Label("Mark applied", systemImage: "checkmark.circle") }
                }
            }
        }
    }
}
