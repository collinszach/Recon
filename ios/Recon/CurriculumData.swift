import Foundation

/// Zach's Berkeley MBA (Haas) + MEng curriculum, lifted from the master plan.
/// Static reference data — the custom 12-unit ME concentration + MBA stack.
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
        CourseGroup(title: "ME Concentration", subtitle: "custom 12-unit build — ML · digital twins · embedded hardware", courses: [
            Course(code: "ME 235", name: "Design of Microprocessor-Based Mechanical Systems", units: "3u",
                   why: "Embedded hardware, sensors, controls — serves Samsara, Rivian, Figure, Zipline."),
            Course(code: "ME 276DS", name: "Statistics & Data Science for Engineers", units: "4u",
                   why: "Full ML course: supervised learning, CNNs, RNNs, time series, in Python. Serves Databricks, NVIDIA, Scale AI."),
            Course(code: "ME 239", name: "Modeling, Simulation & Digital Twins", units: "3u",
                   why: "Digital twins is literally Samsara's category; also Flexport, D365, Rivian."),
            Course(code: "ME 290P", name: "New Product Development", units: "3u",
                   why: "Core PM methodology through the ME department. Rounds the concentration to 12u."),
        ]),
        CourseGroup(title: "MBA Electives", subtitle: "each allocated to a priority domain", courses: [
            Course(code: "MBA 267", name: "Product Management", units: "3u",
                   why: "The flagship PM credential at Haas. Final project = portfolio artifact."),
            Course(code: "MBA 248", name: "Supply Chain Management", units: "3u",
                   why: "Core SCM depth — Samsara, Flexport, Microsoft D365. Your home turf."),
            Course(code: "MBA 295T", name: "Start-up Lab (Applied Innovation)", units: "3u",
                   why: "Project-based entrepreneurship — the founder track."),
            Course(code: "MBA 295C", name: "Opportunity Recognition in Silicon Valley", units: "3u",
                   why: "Venture exposure — Mercury, Crusoe, Databricks adjacency."),
            Course(code: "MBA 290T", name: "Strategy for the Networked Economy", units: "3u",
                   why: "Platform & network effects — Stripe, Plaid, Microsoft, Discord."),
            Course(code: "MBA 231", name: "Corporate Finance", units: "2u",
                   why: "Finance depth beyond intro core — fintech PM + cap-table fluency."),
            Course(code: "MBA 252", name: "Negotiations & Conflict Resolution", units: "2u",
                   why: "Taken early — leverage for spring internship offers."),
        ]),
        CourseGroup(title: "MBA Core", subtitle: "the required Haas core", courses: [
            Course(code: "MBA 200A", name: "Data Analytics", units: "2u", why: "Foundational quant — feeds finance and data courses."),
            Course(code: "MBA 200S", name: "Data and Decisions", units: "2u", why: "Statistics and decision theory."),
            Course(code: "MBA 201A", name: "Economics for Business Decision Making", units: "2u", why: "Micro foundations, competitive advantage."),
            Course(code: "MBA 201B", name: "Macroeconomics in the Global Economy", units: "2u", why: "Global cycles, supply-chain disruption context."),
            Course(code: "MBA 202", name: "Financial Accounting", units: "2u", why: "Reading statements — table stakes for equity diligence."),
            Course(code: "MBA 203", name: "Introduction to Finance", units: "2u", why: "Foundation for fintech PM conversations."),
            Course(code: "MBA 204", name: "Operations", units: "2u", why: "Supply chain and operations adjacency — your home turf."),
            Course(code: "MBA 205", name: "Leading People", units: "2u", why: "Org behavior — foundational for managing eng teams."),
            Course(code: "MBA 206", name: "Marketing", units: "2u", why: "Consumer + B2B framework for go-to-market."),
            Course(code: "MBA 299", name: "Strategic Leadership", units: "2u", why: "Competitive positioning for product/startup strategy."),
            Course(code: "MBA 207", name: "Ethics & Responsible Business Leadership", units: "1u", why: "Relevant when products collect physical/biometric data."),
            Course(code: "MBA 200C", name: "Leadership Communication", units: "1u", why: "Executive and board-level messaging."),
            Course(code: "MBA 205D", name: "Communication in Diverse Environments", units: "1u", why: "Leading diverse technical and business teams."),
        ]),
        CourseGroup(title: "Capstone & MEng", subtitle: "Fung Institute requirements", courses: [
            Course(code: "ENGIN 296MB", name: "MBA/MEng Capstone · Phase 1", units: "1.5u", why: "Scope with a tech-company sponsor."),
            Course(code: "ENGIN 296MB", name: "MBA/MEng Capstone · Phase 2", units: "1.5u", why: "Delivery and final presentation."),
            Course(code: "E270B + E270C", name: "Tech Management & Teaming", units: "2u", why: "General MEng / Fung Institute requirement."),
        ]),
    ]
}
