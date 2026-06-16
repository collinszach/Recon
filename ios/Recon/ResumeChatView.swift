import SwiftUI

/// Collaborative résumé coaching chat. Talks with Zach, asks when unsure, never
/// fabricates, and proposes concrete edits he can apply with one tap.
struct ResumeChatView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss

    @State private var turns: [ChatTurn] = []
    @State private var pendingUpdate: ProposedUpdate?
    @State private var input = ""
    @State private var sending = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 12) {
                            if turns.isEmpty {
                                Text("Your résumé coach. Ask for a critique, help rewriting a bullet, or talk through a new role. It works from your real resume, won't make things up, and keeps it to one page.")
                                    .font(.callout).foregroundStyle(Theme.inkSoft).reconCard()
                            }
                            ForEach(turns) { bubble($0) }
                            if let up = pendingUpdate { proposalCard(up) }
                            if sending {
                                HStack { ProgressView(); Text("Thinking…").font(.caption).foregroundStyle(Theme.inkSoft) }
                            }
                            Color.clear.frame(height: 1).id("bottom")
                        }
                        .padding(16)
                    }
                    .onChange(of: turns.count) { _, _ in withAnimation { proxy.scrollTo("bottom") } }
                }
                inputBar
            }
            .background(Theme.canvas.ignoresSafeArea())
            .navigationTitle("Résumé coach").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }

    private func bubble(_ t: ChatTurn) -> some View {
        let mine = t.role == "user"
        return HStack {
            if mine { Spacer(minLength: 40) }
            Text(t.content)
                .font(.callout)
                .foregroundStyle(mine ? .white : Theme.ink)
                .padding(.horizontal, 12).padding(.vertical, 9)
                .background(mine ? Theme.rust : Theme.card,
                            in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14)
                    .stroke(mine ? .clear : Theme.hair, lineWidth: 1))
                .textSelection(.enabled)
            if !mine { Spacer(minLength: 40) }
        }
    }

    private func proposalCard(_ up: ProposedUpdate) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Proposed change", systemImage: "wand.and.stars")
                .font(.caption.weight(.bold)).foregroundStyle(Theme.gold)
            if let s = up.summary { Text(s).font(.callout).foregroundStyle(Theme.ink) }
            if let e = up.experience, let b = e.bullets {
                Text(b).font(.caption).foregroundStyle(Theme.inkSoft)
            }
            if let p = up.profile, let sum = p.summary {
                Text(sum).font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(4)
            }
            HStack {
                Button("Apply") {
                    Task { await store.applyProposed(up); pendingUpdate = nil
                        turns.append(ChatTurn(role: "user", content: "(applied that change)")) }
                }.buttonStyle(.borderedProminent).tint(Theme.green)
                Button("Dismiss") { pendingUpdate = nil }.buttonStyle(.bordered).tint(Theme.inkSoft)
            }
        }
        .reconCard()
    }

    private var inputBar: some View {
        HStack(spacing: 8) {
            TextField("Message your coach…", text: $input, axis: .vertical)
                .textFieldStyle(.roundedBorder).lineLimit(1...4)
            Button { Task { await send() } } label: {
                Image(systemName: "arrow.up.circle.fill").font(.title2)
            }.tint(Theme.rust).disabled(input.trimmingCharacters(in: .whitespaces).isEmpty || sending)
        }
        .padding(10)
        .background(.ultraThinMaterial)
    }

    private func send() async {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        turns.append(ChatTurn(role: "user", content: text))
        input = ""; sending = true; pendingUpdate = nil
        if let resp = await store.resumeChat(turns) {
            turns.append(ChatTurn(role: "assistant", content: resp.reply))
            pendingUpdate = resp.proposed_update
        }
        sending = false
    }
}
