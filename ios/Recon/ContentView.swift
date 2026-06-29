import SwiftUI

struct ContentView: View {
    @StateObject private var store = Store()
    @State private var showSettings = false

    var body: some View {
        TabView {
            NavTab(title: "Today", store: store, showSettings: $showSettings) { TodayView() }
                .tabItem { Label("Today", systemImage: "sun.max") }

            NavTab(title: "Internships", store: store, showSettings: $showSettings) { RolesView() }
                .tabItem { Label("Roles", systemImage: "dot.radiowaves.left.and.right") }

            NavTab(title: "Pipeline", store: store, showSettings: $showSettings) { PipelineView() }
                .tabItem { Label("Pipeline", systemImage: "rectangle.stack") }

            NavTab(title: "Résumé", store: store, showSettings: $showSettings) { ResumeView() }
                .tabItem { Label("Résumé", systemImage: "doc.text") }

            NavTab(title: "Plan", store: store, showSettings: $showSettings) { PlanView() }
                .tabItem { Label("Plan", systemImage: "map") }
        }
        .tint(Theme.rust)
        .task { if store.roles.isEmpty { await store.refresh() } }
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
