import SwiftUI

/// Actionable offline state. Recon talks to the NUC over Tailscale only, so the
/// usual cause of a failed sync is a dropped VPN, not a dead server. This banner
/// says that plainly, shows how stale the cache is, and gives one-tap recovery
/// (retry + jump to the endpoint picker) instead of a dead "offline" label.
struct ConnectionBanner: View {
    let lastSynced: String?      // e.g. "4d ago", nil if never synced
    let retrying: Bool
    let onRetry: () -> Void
    let onSettings: () -> Void

    private var staleness: String {
        guard let lastSynced else { return "No saved data yet." }
        return "Showing data from \(lastSynced)."
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 11) {
                Image(systemName: "antenna.radiowaves.left.and.right.slash")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(Theme.rust)
                    .accessibilityHidden(true)

                VStack(alignment: .leading, spacing: 3) {
                    Text("Can't reach Recon")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(Theme.ink)
                    Text("\(staleness) Tailscale may be disconnected — reopen it, then retry.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }

            HStack(spacing: 8) {
                Button(action: onRetry) {
                    HStack(spacing: 6) {
                        if retrying {
                            ProgressView().controlSize(.mini).tint(.white)
                        } else {
                            Image(systemName: "arrow.clockwise").font(.caption.weight(.bold))
                        }
                        Text(retrying ? "Reconnecting" : "Retry")
                    }
                }
                .buttonStyle(ReconButtonStyle(color: Theme.rust))
                .disabled(retrying)

                Button(action: onSettings) {
                    Text("Connection")
                }
                .buttonStyle(ReconButtonStyle(color: Theme.rust, soft: true))
                .frame(maxWidth: 130)
            }
        }
        .padding(14)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.corner, style: .continuous)
            .stroke(Theme.rust.opacity(0.30), lineWidth: 1))
        .shadow(color: Color(hex: 0x3A2A18).opacity(0.10), radius: 12, x: 0, y: 5)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Can't reach Recon. \(staleness) Tailscale may be disconnected.")
    }
}
