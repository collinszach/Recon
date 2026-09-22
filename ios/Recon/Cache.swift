import Foundation

/// Tiny on-disk JSON cache so the app shows the last-synced data offline.
enum Cache {
    private static let dir: URL = {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        let d = base.appendingPathComponent("ReconCache", isDirectory: true)
        try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
        return d
    }()

    private static func url(_ name: String) -> URL { dir.appendingPathComponent("\(name).json") }

    /// Writes happen off the main thread.
    ///
    /// These were synchronous, on the main actor, and the roles payload is
    /// hundreds of KB — so every refresh, every swipe and every wipe encoded
    /// and wrote the whole cache before the UI could move again. That is what
    /// "delayed and buggy, especially the load/save" was.
    private static let io = DispatchQueue(label: "recon.cache", qos: .utility)

    static func save<T: Encodable & Sendable>(_ value: T, _ name: String) {
        io.async {
            do { try JSONEncoder().encode(value).write(to: url(name), options: .atomic) }
            catch { /* best-effort cache; ignore */ }
        }
    }

    static func load<T: Decodable>(_ type: T.Type, _ name: String) -> T? {
        guard let data = try? Data(contentsOf: url(name)) else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }
}
