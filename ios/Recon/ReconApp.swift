import SwiftUI

@main
struct ReconApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .preferredColorScheme(nil) // follow system; dashboard supplies its own palette
        }
    }
}
