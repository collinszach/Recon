import SwiftUI

/// Palette lifted from the Recon master-plan dashboard so the native UI feels
/// like the same product.
enum Theme {
    static let paper   = Color(red: 0.957, green: 0.937, blue: 0.902) // #F4EFE6
    static let card    = Color(red: 1.0,   green: 0.992, blue: 0.976) // near-white warm
    static let ink     = Color(red: 0.169, green: 0.137, blue: 0.122) // #2B2320
    static let inkSoft = Color(red: 0.40,  green: 0.36,  blue: 0.34)
    static let rust    = Color(red: 0.710, green: 0.325, blue: 0.184) // #B5532F
    static let gold    = Color(red: 0.788, green: 0.635, blue: 0.255) // #C9A241
    static let green   = Color(red: 0.310, green: 0.478, blue: 0.290) // #4F7A4A
    static let hair    = Color(red: 0.847, green: 0.812, blue: 0.760) // hairline

    /// Color for a fit tier badge (A/B/C/pass).
    static func tier(_ t: String?) -> Color {
        switch (t ?? "").uppercased() {
        case "A": return green
        case "B": return rust
        case "C": return gold
        default:  return inkSoft          // pass / unknown
        }
    }

    /// Color for a fit score 0–10.
    static func fit(_ s: Double?) -> Color {
        guard let s else { return inkSoft }
        if s >= 8 { return green }
        if s >= 6 { return rust }
        return inkSoft
    }
}

extension View {
    /// Standard warm card surface used across the app.
    func reconCard() -> some View {
        self.padding(14)
            .background(Theme.card, in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.hair, lineWidth: 1))
    }
}
