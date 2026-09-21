import SwiftUI

struct ContentView: View {
    @StateObject private var store = Store()
    @State private var showSettings = false

    var body: some View {
        TabView {
            NavTab(title: "Dashboard", store: store, showSettings: $showSettings) { TodayView() }
                .tabItem { Label("Dashboard", systemImage: "square.grid.2x2") }

            NavTab(title: "Roles", store: store, showSettings: $showSettings) { RolesView() }
                .tabItem { Label("Roles", systemImage: "dot.radiowaves.left.and.right") }

            NavTab(title: "Pipeline", store: store, showSettings: $showSettings) { PipelineView() }
                .tabItem { Label("Pipeline", systemImage: "rectangle.stack") }

            NavTab(title: "Startups", store: store, showSettings: $showSettings) { StartupsView() }
                .tabItem { Label("Startups", systemImage: "building.2") }

            NavTab(title: "Résumé", store: store, showSettings: $showSettings) { ResumeView() }
                .tabItem { Label("Résumé", systemImage: "doc.text") }

            NavTab(title: "Plan", store: store, showSettings: $showSettings) { PlanView() }
                .tabItem { Label("Plan", systemImage: "map") }
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
        .sheet(isPresented: $showSettings) {
            SettingsView { Task { await store.refresh() } }
        }
    }
}

/// Wraps a tab screen in a NavigationStack with the shared store, a refresh
/// toolbar button, and a settings gear.
private struct NavTab<Content: View>: View {
    let title: String
    @ObservedObject var store: Store
    @Binding var showSettings: Bool
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
                        Button { showSettings = true } label: { Image(systemName: "gearshape") }
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
                            onSettings: { showSettings = true }
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
