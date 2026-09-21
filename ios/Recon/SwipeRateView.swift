import SwiftUI

/// Fast triage over new arrivals: swipe right = track it (POST /api/applications,
/// "watching" — the reason to come back and actually apply), left = wipe it
/// (POST /api/roles/{id}/dismiss, permanent and gone after re-ingest).
///
/// This was the scoring-calibration deck; with the scorer off (2026-09-21) a
/// rating has nothing to calibrate, so the same gesture now does the two things
/// a tracker cares about — keep or wipe.
struct SwipeRateView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss
    @State private var deck: [Role]
    @State private var dragOffset: CGSize = .zero
    @State private var rated = 0

    init(deck: [Role]) {
        _deck = State(initialValue: deck)
    }

    private let swipeThreshold: CGFloat = 110

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.canvas.ignoresSafeArea()
                VStack(spacing: 18) {
                    if deck.isEmpty {
                        emptyState
                    } else {
                        Text("\(deck.count) to triage")
                            .font(.caption.weight(.semibold)).foregroundStyle(Theme.inkSoft)
                            .padding(.top, 4)
                        cardStack
                        if let top = deck.first {
                            NavigationLink(value: top) {
                                Label("Full listing — location, JD, company", systemImage: "doc.text.magnifyingglass")
                                    .font(.caption.weight(.medium))
                            }
                            .foregroundStyle(Theme.rust)
                        }
                        actionButtons
                    }
                }
                .padding(16)
            }
            .navigationTitle("Rate Roles")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: Role.self) { RoleDetailView(role: $0, store: store) }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    NavigationLink { RatedRolesView().environmentObject(store) } label: {
                        Label("Your ratings", systemImage: "clock.arrow.circlepath")
                    }
                    .tint(Theme.rust)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 10) {
            Image(systemName: "checkmark.circle").font(.system(size: 40)).foregroundStyle(Theme.green)
            Text(rated > 0 ? "Triaged \(rated) role\(rated == 1 ? "" : "s") — nice work." : "Nothing new to triage right now.")
                .font(.subheadline.weight(.medium)).foregroundStyle(Theme.ink)
            Text("New roles show up here as Recon scores them.")
                .font(.caption).foregroundStyle(Theme.inkSoft)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 100)
    }

    /// Up to 3 cards deep, back-to-front so SwiftUI draws index 0 (the
    /// interactive top card) last / on top. A plain named-tuple array,
    /// computed outside the ForEach call — inlining .enumerated().reversed()
    /// directly in the ForEach initializer made the compiler pick the wrong
    /// overload (one expecting a Binding<C>, meant for editable lists).
    private var topCards: [(idx: Int, role: Role)] {
        Array(deck.prefix(3).enumerated()).reversed().map { (idx: $0.offset, role: $0.element) }
    }

    private var cardStack: some View {
        ZStack {
            ForEach(topCards, id: \.role.id) { item in
                stackedCard(idx: item.idx, role: item.role)
            }
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private func stackedCard(idx: Int, role: Role) -> some View {
        let isTop = idx == 0
        let card = RateCard(role: role)
            .padding(.horizontal, 4)
            .scaleEffect(isTop ? 1 : 1 - CGFloat(idx) * 0.04)
            .offset(y: isTop ? 0 : CGFloat(idx) * 10)
            .offset(isTop ? dragOffset : .zero)
            .rotationEffect(.degrees(isTop ? Double(dragOffset.width / 18) : 0))
            .zIndex(isTop ? 1 : 0)
        if isTop {
            card
                .overlay(stampOverlay)
                .gesture(dragGesture(for: role))
                .animation(.spring(response: 0.35, dampingFraction: 0.8), value: dragOffset)
        } else {
            card
        }
    }

    @ViewBuilder
    private var stampOverlay: some View {
        if dragOffset.width > 30 {
            stamp(text: "INTERESTED", color: Theme.green)
                .opacity(min(1, Double(dragOffset.width / swipeThreshold)))
        } else if dragOffset.width < -30 {
            stamp(text: "PASS", color: Theme.rust)
                .opacity(min(1, Double(-dragOffset.width / swipeThreshold)))
        }
    }

    private func stamp(text: String, color: Color) -> some View {
        Text(text)
            .font(.headline.weight(.heavy)).tracking(1.2)
            .foregroundStyle(color)
            .padding(.horizontal, 14).padding(.vertical, 8)
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(color, lineWidth: 3))
            .rotationEffect(.degrees(-12))
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .padding(.top, 28)
    }

    private var actionButtons: some View {
        HStack(spacing: 28) {
            Button { commit(deck.first, value: "down") } label: {
                Image(systemName: "xmark").font(.title2.weight(.bold))
                    .foregroundStyle(Theme.rust)
                    .frame(width: 58, height: 58)
                    .background(Theme.card, in: Circle())
                    .overlay(Circle().stroke(Theme.hair))
            }
            Button { commit(deck.first, value: "up") } label: {
                Image(systemName: "heart.fill").font(.title2.weight(.bold))
                    .foregroundStyle(Theme.green)
                    .frame(width: 58, height: 58)
                    .background(Theme.card, in: Circle())
                    .overlay(Circle().stroke(Theme.hair))
            }
        }
        .disabled(deck.isEmpty)
        .padding(.bottom, 8)
    }

    private func dragGesture(for role: Role) -> some Gesture {
        DragGesture()
            .onChanged { dragOffset = $0.translation }
            .onEnded { value in
                if value.translation.width > swipeThreshold {
                    commit(role, value: "up")
                } else if value.translation.width < -swipeThreshold {
                    commit(role, value: "down")
                } else {
                    dragOffset = .zero
                }
            }
    }

    private func commit(_ role: Role?, value: String) {
        guard let role, role.id == deck.first?.id else { return }
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        let flyDistance: CGFloat = value == "up" ? 500 : -500
        withAnimation(.easeOut(duration: 0.25)) { dragOffset = CGSize(width: flyDistance, height: 0) }
        Task {
            if value == "up" {
                await store.setInterest(role, "up")
                await store.track(role)
            } else {
                await store.dismiss(role)
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.22) {
            deck.removeAll { $0.id == role.id }
            rated += 1
            dragOffset = .zero
        }
    }
}

/// One role, card-sized — trimmed to what matters for a quick yes/no call.
private struct RateCard: View {
    let role: Role
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                if role.firstSeenIsToday { Pill(text: "New", color: Theme.gold, filled: true) }
                if role.isMba == true { Pill(text: "MBA", color: Theme.rust) }
                Spacer()
                if let seen = role.firstSeenText {
                    Text(seen).font(.caption2).foregroundStyle(Theme.inkSoft)
                }
            }
            Text(role.company ?? "—").font(.title3.weight(.bold)).foregroundStyle(Theme.ink)
            Text(role.title).font(.headline).foregroundStyle(Theme.ink)

            HStack(spacing: 10) {
                Label(role.pay, systemImage: "dollarsign.circle")
                    .font(.caption).foregroundStyle(Theme.green)
                if let loc = role.location, !loc.isEmpty {
                    Label(loc, systemImage: "mappin.and.ellipse")
                        .font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(1)
                }
            }

            Divider().background(Theme.hair)

            // Fixed line limits, not a ScrollView — a scrollable region inside
            // a swipeable card steals the drag gesture the instant a touch
            // starts over it (confirmed: dragging from the text area did
            // nothing, dragging from the header above it worked fine). Full
            // text is one tap away on RoleDetailView; this card is a quick
            // yes/no glance, not the place to read the whole rationale.
            VStack(alignment: .leading, spacing: 8) {
                Text("WHY IT SCORED THIS WAY").font(.caption2.weight(.bold))
                    .tracking(0.6).foregroundStyle(Theme.rust)
                Text(role.summary).font(.subheadline).foregroundStyle(Theme.ink)
                    .lineLimit(role.concerns?.isEmpty == false ? 5 : 9)
                if let concerns = role.concerns, !concerns.isEmpty {
                    Text("WATCH FOR").font(.caption2.weight(.bold))
                        .tracking(0.6).foregroundStyle(Theme.gold).padding(.top, 4)
                    Text(concerns).font(.subheadline).foregroundStyle(Theme.inkSoft)
                        .lineLimit(3)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(18)
        .frame(maxWidth: .infinity, minHeight: 380, maxHeight: 420, alignment: .top)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.corner, style: .continuous).stroke(Theme.hair, lineWidth: 0.75))
        .shadow(color: Color(hex: 0x3A2A18).opacity(0.12), radius: 16, x: 0, y: 8)
    }
}
