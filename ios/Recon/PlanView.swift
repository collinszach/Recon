import SwiftUI

/// Native Plan: the curriculum and the target-company breakdown (replaces the
/// old web dashboard).
struct PlanView: View {
    @State private var seg = "curriculum"

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $seg) {
                Text("Curriculum").tag("curriculum")
                Text("Companies").tag("companies")
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 16).padding(.bottom, 8)

            if seg == "curriculum" { CurriculumView() } else { CompaniesView() }
        }
    }
}

private struct CurriculumView: View {
    var totalUnits: Double {
        Curriculum.groups.flatMap(\.courses)
            .compactMap { Double($0.units.replacingOccurrences(of: "u", with: "")) }
            .reduce(0, +)
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Stat(num: String(format: "%g", totalUnits), label: "total units", color: Theme.rust)
                    Stat(num: "12", label: "ME concentration", color: Theme.gold)
                    Stat(num: "'28", label: "MBA + MEng", color: Theme.green)
                }
                ForEach(Curriculum.groups) { g in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(g.title).font(.headline).foregroundStyle(Theme.ink)
                        Text(g.subtitle).font(.caption).foregroundStyle(Theme.inkSoft)
                        ForEach(g.courses) { c in courseRow(c) }
                    }
                }
            }
            .padding(16)
        }
        .scrollContentBackground(.hidden)
    }
    private func courseRow(_ c: Course) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(c.code).font(.caption.monospaced().weight(.semibold)).foregroundStyle(Theme.rust)
                Spacer()
                Text(c.units).font(.caption2).foregroundStyle(Theme.inkSoft)
            }
            Text(c.name).font(.subheadline.weight(.medium)).foregroundStyle(Theme.ink)
            Text(c.why).font(.caption).foregroundStyle(Theme.inkSoft)
        }
        .reconCard()
    }
}

private struct CompaniesView: View {
    @EnvironmentObject var store: Store
    private let tiers: [(String, String)] = [("A", "Tier A — primary"),
                                              ("B", "Tier B — strong swings"),
                                              ("C", "Tier C — lifestyle / early / breadth")]
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if store.companies.isEmpty {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 40)
                }
                ForEach(tiers, id: \.0) { tier, label in
                    let cos = store.companies.filter { $0.tier == tier }
                    if !cos.isEmpty {
                        Text(label).font(.headline).foregroundStyle(Theme.ink)
                        ForEach(cos) { companyCard($0) }
                    }
                }
            }
            .padding(16)
        }
        .scrollContentBackground(.hidden)
        .task { if store.companies.isEmpty { await store.loadCompanies() } }
    }
    private func companyCard(_ c: Company) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(c.name).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Spacer()
                if let d = c.domain {
                    Text(d).font(.caption2.weight(.medium)).foregroundStyle(Theme.rust)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Theme.rust.opacity(0.12), in: Capsule())
                }
            }
            if let b = c.blurb { Text(b).font(.caption).foregroundStyle(Theme.inkSoft) }
            HStack(spacing: 12) {
                Label("\(c.surfaced) surfaced", systemImage: "sparkle")
                    .font(.caption2).foregroundStyle(Theme.green)
                Label("\(c.tracked) tracked", systemImage: "dot.radiowaves.left.and.right")
                    .font(.caption2).foregroundStyle(Theme.inkSoft)
                Spacer()
                if let u = c.careersUrl, let url = URL(string: u) {
                    Link("Careers", destination: url).font(.caption2)
                }
            }
        }
        .reconCard()
    }
}
