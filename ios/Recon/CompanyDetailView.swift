import SwiftUI

/// One tracked company: what Recon knows about it, and the last month of news
/// (funding, layoffs, freezes, leadership changes) that bears on applying there.
struct CompanyDetailView: View {
    let company: Company
    @State private var news: [CompanyNews] = []
    @State private var loaded = false
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header
                SectionHeader(title: "News", eyebrow: "Last 30 days",
                              trailing: news.isEmpty ? nil : "\(news.count)")
                newsSection
            }
            .padding(16)
        }
        .scrollContentBackground(.hidden)
        .reconBackground()
        .navigationTitle(company.name)
        .navigationBarTitleDisplayMode(.inline)
        .task { if !loaded { await load() } }
        .refreshable { await load() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                if let t = company.tier {
                    Text("Tier \(t)").font(.caption2.weight(.bold)).foregroundStyle(Theme.tier(t))
                }
                if let d = company.domain {
                    Text(d).font(.caption2.weight(.medium)).foregroundStyle(Theme.rust)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Theme.rust.opacity(0.12), in: Capsule())
                }
                Spacer()
            }
            if let b = company.blurb { Text(b).font(.subheadline).foregroundStyle(Theme.ink) }
            HStack(spacing: 12) {
                Label("\(company.tracked) open roles", systemImage: "dot.radiowaves.left.and.right")
                    .font(.caption).foregroundStyle(Theme.inkSoft)
                Spacer()
                if let u = company.careersUrl, let url = URL(string: u) {
                    Link("Careers", destination: url).font(.caption.weight(.semibold))
                }
            }
        }
        .reconCard()
    }

    @ViewBuilder private var newsSection: some View {
        if !loaded {
            ProgressView().frame(maxWidth: .infinity).padding(.top, 24)
        } else if let error, news.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text("Couldn't load news").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Text(error).font(.caption).foregroundStyle(Theme.inkSoft)
                Button("Try again") { Task { await load() } }.font(.caption.weight(.semibold))
            }
            .reconCard()
        } else if news.isEmpty {
            Text("No news in the last 30 days. Recon checks each tracked company every day or two.")
                .font(.caption).foregroundStyle(Theme.inkSoft)
                .frame(maxWidth: .infinity, alignment: .leading)
                .reconCard()
        } else {
            ForEach(news) { NewsRow(item: $0) }
        }
    }

    private func load() async {
        do {
            news = try await ReconAPI.shared.companyNews(company.id)
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loaded = true
    }
}

/// A headline, its tags, and where/when it ran. Tapping opens the article.
struct NewsRow: View {
    let item: CompanyNews

    var body: some View {
        let content = VStack(alignment: .leading, spacing: 6) {
            if !item.tags.isEmpty {
                HStack(spacing: 6) {
                    ForEach(item.tags, id: \.self) { tag in
                        Text(CompanyNews.label(tag))
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(CompanyNews.color(tag))
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(CompanyNews.color(tag).opacity(0.12), in: Capsule())
                    }
                }
            }
            Text(item.title).font(.subheadline.weight(.medium)).foregroundStyle(Theme.ink)
                .multilineTextAlignment(.leading)
            if let d = item.description, !d.isEmpty {
                Text(d).font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(3)
                    .multilineTextAlignment(.leading)
            }
            Text([item.source, item.publishedAt.map { ago($0) }].compactMap { $0 }.joined(separator: " · "))
                .font(.caption2).foregroundStyle(Theme.inkSoft)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .reconCard(14)

        if let url = URL(string: item.url) {
            Link(destination: url) { content }
                .accessibilityHint("Opens the article")
        } else {
            content
        }
    }
}
