import SwiftUI

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255, opacity: 1)
    }
}

/// Recon design system — warm editorial palette with modern iOS depth.
enum Theme {
    // Canvas
    static let paper   = Color(hex: 0xF3EDE2)   // warm canvas (top)
    static let paper2  = Color(hex: 0xEBE3D4)   // canvas (bottom, for gradient)
    static let card    = Color(hex: 0xFFFDF8)   // elevated surface
    static let hair    = Color(hex: 0xE7DECF)   // hairline

    // Ink
    static let ink     = Color(hex: 0x231C16)   // primary text
    static let inkSoft = Color(hex: 0x6E6457)   // secondary text

    // Accents
    static let rust    = Color(hex: 0xB5532F)
    static let rustDeep = Color(hex: 0x8F3D1F)
    static let gold    = Color(hex: 0xC2922E)
    static let green   = Color(hex: 0x4F7A4A)

    static let corner: CGFloat = 18

    /// Warm screen background gradient.
    static var canvas: LinearGradient {
        LinearGradient(colors: [paper, paper2], startPoint: .top, endPoint: .bottom)
    }

    /// Color for a fit tier badge (A/B/C/pass).
    static func tier(_ t: String?) -> Color {
        switch (t ?? "").uppercased() {
        case "A": return green
        case "B": return rust
        case "C": return gold
        default:  return inkSoft
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
    /// Elevated card surface: continuous corners + soft warm shadow + hairline.
    func reconCard(_ padding: CGFloat = 16) -> some View {
        self.padding(padding)
            .background(Theme.card, in: RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Theme.corner, style: .continuous)
                .stroke(Theme.hair, lineWidth: 0.75))
            .shadow(color: Color(hex: 0x3A2A18).opacity(0.07), radius: 10, x: 0, y: 4)
    }

    /// Full-screen warm gradient background.
    func reconBackground() -> some View {
        self.background(Theme.canvas.ignoresSafeArea())
    }
}

/// A small uppercase eyebrow + title section header.
struct SectionHeader: View {
    let title: String
    var eyebrow: String? = nil
    var trailing: String? = nil
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 1) {
                if let e = eyebrow {
                    Text(e.uppercased()).font(.caption2.weight(.bold))
                        .tracking(0.8).foregroundStyle(Theme.rust)
                }
                Text(title).font(.title3.weight(.semibold)).foregroundStyle(Theme.ink)
            }
            Spacer()
            if let t = trailing {
                Text(t).font(.caption.weight(.medium)).foregroundStyle(Theme.inkSoft)
            }
        }
    }
}

/// Small colored pill (tier / status / tag).
struct Pill: View {
    let text: String
    var color: Color = Theme.rust
    var filled: Bool = false
    var body: some View {
        Text(text.uppercased()).font(.caption2.weight(.bold)).tracking(0.4)
            .foregroundStyle(filled ? .white : color)
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(filled ? color : color.opacity(0.14), in: Capsule())
    }
}

/// Prominent pill-shaped accent button.
struct ReconButtonStyle: ButtonStyle {
    var color: Color = Theme.rust
    var soft: Bool = false
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.semibold))
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .foregroundStyle(soft ? color : .white)
            .background(soft ? color.opacity(0.12) : color,
                        in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .opacity(configuration.isPressed ? 0.85 : 1)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}
