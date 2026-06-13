import SwiftUI

/// The full master-plan dashboard, shown in a web view. Kept as a reference tab —
/// the day-to-day surfaces (Today / Roles / Pipeline) are native.
struct PlanView: View {
    @StateObject private var config = AppConfig.shared
    @State private var isLoading = false
    @State private var loadError: String?
    @State private var reload = 0

    var body: some View {
        ZStack {
            WebView(url: config.baseURL, isLoading: $isLoading,
                    loadError: $loadError, reloadToken: reload)
                .ignoresSafeArea(edges: .bottom)
            if isLoading && loadError == nil {
                ProgressView().padding(16)
                    .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
            }
            if let err = loadError {
                VStack(spacing: 12) {
                    Image(systemName: "wifi.exclamationmark").font(.largeTitle)
                    Text("Can't load the dashboard").font(.headline)
                    Text(err).font(.footnote).foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                    Button("Retry") { loadError = nil; reload += 1 }
                        .buttonStyle(.borderedProminent).tint(Theme.rust)
                }.padding(24).reconCard().padding()
            }
        }
    }
}
