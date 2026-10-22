import SwiftUI

struct ContentView: View {
    @StateObject private var store = Store()
    @State private var sheet: ProfileSheet?

    var body: some View {
        // Three tabs, one job each: what changed (Today), what's out there
        // (Jobs), what you've sent (Applications). Everything else is behind
        // the profile menu — seven tabs made the daily path hard to find.
        TabView {
            NavTab(title: "Today", store: store, sheet: $sheet) { TodayView() }
                .tabItem { Label("Today", systemImage: "sun.max") }
                .badge(store.mailProposals.count)

            NavTab(title: "Jobs", store: store, sheet: $sheet) { JobsView() }
                .tabItem { Label("Jobs", systemImage: "magnifyingglass") }

            NavTab(title: "Applications", store: store, sheet: $sheet) { PipelineView() }
                .tabItem { Label("Applications", systemImage: "tray.full") }
        }
        .tint(Theme.rust)
        // Always refresh on launch, not just when the cache is empty — Store.init()
        // loads a local disk cache synchronously, so gating on isEmpty meant the app
        // would silently keep showing a stale snapshot forever after the first-ever
        // successful fetch (2026-08-16: this is why new fields like `state` never
        // appeared — cached roles predated them, and launch never refetched).
        // refresh() already falls back to the cache gracefully on failure (see
        // handleLoadFailure), so this is safe even fully offline.
        .task { await store.refresh() }
        .sheet(item: $sheet) { which in
            switch which {
            case .settings:
                SettingsView { Task { await store.refresh() } }.environmentObject(store)
            case .resume:
                ProfilePage(title: "Résumé") { ResumeView() }.environmentObject(store)
            case .plan:
                ProfilePage(title: "Plan") { PlanView() }.environmentObject(store)
            }
        }
    }
}

/// What lives behind the profile menu.
enum ProfileSheet: String, Identifiable {
    case resume, plan, settings
    var id: String { rawValue }
}

/// A profile-menu screen: its own navigation, a Done button, the shared store.
private struct ProfilePage<Content: View>: View {
    let title: String
    @ViewBuilder var content: () -> Content
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            content()
                .environmentObject(store)
                .reconBackground()
                .navigationTitle(title)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }
}

/// Finding work: roles from every board, the ones you've kept and still need
/// to submit, and the startups Recon watches.
struct JobsView: View {
    @EnvironmentObject var store: Store
    @State private var seg = Segment.roles
    enum Segment: String, CaseIterable, Identifiable {
        case roles = "Roles", toApply = "To apply", startups = "Startups"
        var id: String { rawValue }
    }
    var body: some View {
        VStack(spacing: 0) {
            Picker("Show", selection: $seg) {
                ForEach(Segment.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented).padding(.horizontal, 16).padding(.bottom, 8)
            switch seg {
            case .roles:    RolesView()
            case .toApply:  ApplyView()
            case .startups: StartupsView()
            }
        }
    }
}

/// Wraps a tab screen in a NavigationStack with the shared store, a refresh
/// toolbar button, and a settings gear.
private struct NavTab<Content: View>: View {
    let title: String
    @ObservedObject var store: Store
    @Binding var sheet: ProfileSheet?
    @ViewBuilder var content: () -> Content

    var body: some View {
        NavigationStack {
            content()
                .environmentObject(store)
                .reconBackground()
                .navigationTitle(title)
                .navigationBarTitleDisplayMode(.large)
                .toolbar {
                    ToolbarItem(placement: .topBarLeading) {
                        if store.loading { ProgressView() }
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        Menu {
                            Button { sheet = .resume } label: { Label("Résumé", systemImage: "doc.text") }
                            Button { sheet = .plan } label: { Label("Plan", systemImage: "map") }
                            Divider()
                            Button { sheet = .settings } label: { Label("Settings", systemImage: "gearshape") }
                        } label: {
                            Image(systemName: "person.crop.circle")
                                .accessibilityLabel("Profile: résumé, plan, settings")
                        }
                    }
                }
                .refreshable { await store.refresh() }
                .safeAreaInset(edge: .top) {
                    if store.isOffline {
                        ConnectionBanner(
                            lastSynced: store.lastSyncedText,
                            retrying: store.loading,
                            detail: store.error,
                            onRetry: { Task { await store.refresh() } },
                            onSettings: { sheet = .settings }
                        )
                        .padding(.horizontal, 16)
                        .padding(.top, 6)
                        .transition(.move(edge: .top).combined(with: .opacity))
                    }
                }
                .animation(.easeOut(duration: 0.28), value: store.isOffline)
        }
    }
}

#Preview { ContentView() }
