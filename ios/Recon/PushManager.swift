import UIKit
import UserNotifications

/// Registers for APNs on launch and forwards the device token to the Recon
/// backend (POST /api/push/register-device). Delivery itself is server-driven —
/// the scan pipeline pushes the moment a new high-fit role/startup update lands
/// (see api/notify/apns.py); this class only handles the one-time handshake.
final class PushManager: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(_ application: UIApplication,
                      didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            guard granted else { return }
            DispatchQueue.main.async { application.registerForRemoteNotifications() }
        }
        return true
    }

    func application(_ application: UIApplication,
                      didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        Task {
            try? await ReconAPI.shared.registerDevice(token: token)
        }
    }

    func application(_ application: UIApplication,
                      didFailToRegisterForRemoteNotificationsWithError error: Error) {
        // No-op: push is a nice-to-have, never block the app on it.
    }

    /// Show the alert even while the app is in the foreground.
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                 willPresent notification: UNNotification) async
        -> UNNotificationPresentationOptions {
        [.banner, .sound, .badge]
    }
}
