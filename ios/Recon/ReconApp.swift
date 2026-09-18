import SwiftUI

@main
struct ReconApp: App {
    @UIApplicationDelegateAdaptor(PushManager.self) var pushManager

    var body: some Scene {
        WindowGroup {
            ContentView()
                .preferredColorScheme(nil) // follow system; dashboard supplies its own palette
        }
    }
}
