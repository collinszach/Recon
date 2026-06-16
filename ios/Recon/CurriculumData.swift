import Foundation

/// Zach's Berkeley MBA (Haas) + MEng curriculum, by semester. The custom 12-unit
/// ME concentration (ME 235 / 276DS / 239 / 290P) threads across the four terms.
struct Course: Identifiable, Hashable {
    let id = UUID()
    let code: String
    let name: String
    let units: String
    let why: String
}

struct CourseGroup: Identifiable, Hashable {
    let id = UUID()
    let title: String
    let subtitle: String
    let courses: [Course]
}

enum Curriculum {
    static let groups: [CourseGroup] = [
        CourseGroup(title: "Fall 2026", subtitle: "Year 1 · MBA core + embedded-hardware anchor", courses: [
            Course(code: "ME 235", name: "Microprocessor-Based Mechanical Systems", units: "3u",
                   why: "Concentration 1/4 — embedded hardware, sensors, controls. Serves Samsara, Rivian, Figure, Zipline."),
            Course(code: "MBA 200A", name: "Data Analytics", units: "2u", why: "Foundational quant — feeds finance and data courses."),
            Course(code: "MBA 201A", name: "Economics for Business Decision Making", units: "2u", why: "Micro foundations, competitive advantage."),
            Course(code: "MBA 202", name: "Financial Accounting", units: "2u", why: "Reading statements — table stakes for equity diligence."),
            Course(code: "MBA 205", name: "Leading People", units: "2u", why: "Org behavior — foundational for managing eng teams."),
            Course(code: "MBA 206", name: "Marketing", units: "2u", why: "Consumer + B2B framework for go-to-market."),
            Course(code: "MBA 252", name: "Negotiations & Conflict Resolution", units: "2u", why: "Taken early — leverage for spring internship offers."),
        ]),
        CourseGroup(title: "Spring 2027", subtitle: "Year 1 · ML anchor + flagship PM", courses: [
            Course(code: "ME 276DS", name: "Statistics & Data Science for Engineers", units: "4u",
                   why: "Concentration 2/4 — full ML course (supervised learning, CNNs, RNNs, time series, Python). Databricks, NVIDIA, Scale AI."),
            Course(code: "MBA 267", name: "Product Management", units: "3u", why: "The flagship PM credential at Haas. Final project = portfolio artifact."),
            Course(code: "MBA 200S", name: "Data and Decisions", units: "2u", why: "Statistics and decision theory."),
            Course(code: "MBA 203", name: "Introduction to Finance", units: "2u", why: "Foundation for fintech PM conversations."),
            Course(code: "MBA 204", name: "Operations", units: "2u", why: "Supply chain and operations adjacency — your home turf."),
            Course(code: "MBA 201B", name: "Macroeconomics in the Global Economy", units: "2u", why: "Global cycles, supply-chain disruption context."),
        ]),
        CourseGroup(title: "Summer 2027", subtitle: "the domain bet — no classes", courses: [
            Course(code: "INTERNSHIP", name: "Summer 2027 product/APM internship", units: "—",
                   why: "12 weeks at a primary target (Samsara, Microsoft, Databricks, Rivian) — ship a feature, aim for a return offer."),
            Course(code: "TMB", name: "Tour du Mont Blanc", units: "—",
                   why: "~110 miles, 35K+ ft of climbing, in August — the marquee trip at peak fitness."),
        ]),
        CourseGroup(title: "Fall 2027", subtitle: "Year 2 · concentration + SCM/twins + startup lab", courses: [
            Course(code: "ME 239", name: "Modeling, Simulation & Digital Twins", units: "3u",
                   why: "Concentration 3/4 — digital twins is literally Samsara's category; also Flexport, D365, Rivian."),
            Course(code: "MBA 248", name: "Supply Chain Management", units: "3u", why: "Core SCM depth — Samsara, Flexport, Microsoft D365. Your home turf."),
            Course(code: "MBA 295T", name: "Start-up Lab (Applied Innovation)", units: "3u", why: "Project-based entrepreneurship — the founder track."),
            Course(code: "MBA 299", name: "Strategic Leadership", units: "2u", why: "Competitive positioning for product/startup strategy."),
            Course(code: "MBA 207", name: "Ethics & Responsible Business Leadership", units: "1u", why: "Relevant when products collect physical/biometric data."),
            Course(code: "ENGIN 296MB", name: "MBA/MEng Capstone · Phase 1", units: "1.5u", why: "Scope with a tech-company sponsor."),
        ]),
        CourseGroup(title: "Spring 2028", subtitle: "Year 2 · deliver & launch — venture, finance, NPD", courses: [
            Course(code: "ME 290P", name: "New Product Development", units: "3u",
                   why: "Concentration 4/4 — core PM methodology through the ME dept. Rounds the concentration to 12u."),
            Course(code: "MBA 290T", name: "Strategy for the Networked Economy", units: "3u", why: "Platform & network effects — Stripe, Plaid, Microsoft, Discord."),
            Course(code: "MBA 295C", name: "Opportunity Recognition in Silicon Valley", units: "3u", why: "Venture exposure — Mercury, Crusoe, Databricks adjacency."),
            Course(code: "MBA 231", name: "Corporate Finance", units: "2u", why: "Finance depth beyond intro core — fintech PM + cap-table fluency."),
            Course(code: "E270B + E270C", name: "Tech Management & Teaming", units: "2u", why: "General MEng / Fung Institute requirement."),
            Course(code: "MBA 200C", name: "Leadership Communication", units: "1u", why: "Executive and board-level messaging."),
            Course(code: "MBA 205D", name: "Communication in Diverse Environments", units: "1u", why: "Leading diverse technical and business teams."),
            Course(code: "ENGIN 296MB", name: "MBA/MEng Capstone · Phase 2", units: "1.5u", why: "Delivery and final presentation."),
        ]),
    ]
}
