import SwiftUI

/// The standing answers every application form asks for, in one place.
///
/// These used to live only in the Chrome extension's options page, which meant
/// the phone could show you a role, queue it, and open the form — and then had
/// nothing to put in it. `autofillReady` gates on an email the app had no way to
/// set, so Fill was permanently disabled on a fresh install. This is that gap.
///
/// The résumé supplies name, headline and location; everything here is the rest.
struct AutofillProfileView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss

    @State private var f: [String: String] = [:]
    @State private var workAuthorized: Bool?
    @State private var requiresSponsorship: Bool?
    @State private var willingToRelocate: Bool?
    @State private var saving = false
    @State private var error: String?

    /// Text keys, in the order the form shows them.
    private static let textKeys = [
        "email", "phone",
        "address_line1", "city", "state", "zip_code", "country",
        "linkedin_url", "github_url", "portfolio_url",
        "desired_salary", "earliest_start_date", "notice_period", "how_heard",
        "pronouns", "gender", "race_ethnicity", "veteran_status", "disability_status",
    ]

    var body: some View {
        NavigationStack {
            Form {
                if let error {
                    Section { Text(error).font(.footnote).foregroundStyle(.red) }
                }

                Section {
                    field("email", "Email", keyboard: .emailAddress)
                    field("phone", "Phone", keyboard: .phonePad)
                } header: { Text("Contact") } footer: {
                    Text(store.autofillReady
                         ? "Fill is enabled."
                         : "Fill stays disabled until there's a first name, last name and email. Name comes from your résumé.")
                    .font(.footnote)
                }

                Section("Address") {
                    field("address_line1", "Street")
                    field("city", "City")
                    field("state", "State")
                    field("zip_code", "ZIP")
                    field("country", "Country")
                }

                Section("Links") {
                    field("linkedin_url", "LinkedIn", keyboard: .URL)
                    field("github_url", "GitHub", keyboard: .URL)
                    field("portfolio_url", "Portfolio", keyboard: .URL)
                }

                Section {
                    tristate("Authorized to work in the US", $workAuthorized)
                    tristate("Requires sponsorship", $requiresSponsorship)
                    tristate("Willing to relocate", $willingToRelocate)
                } header: { Text("Work authorization") } footer: {
                    Text("Left unset, these are skipped rather than guessed.")
                        .font(.footnote)
                }

                Section("Preferences") {
                    field("desired_salary", "Desired salary")
                    field("earliest_start_date", "Earliest start")
                    field("notice_period", "Notice period")
                    field("how_heard", "How you heard")
                }

                Section {
                    field("pronouns", "Pronouns")
                    field("gender", "Gender")
                    field("race_ethnicity", "Race / ethnicity")
                    field("veteran_status", "Veteran status")
                    field("disability_status", "Disability status")
                } header: { Text("Self-identification") } footer: {
                    Text("Optional everywhere, and only ever written into a field whose label actually asks for it.")
                        .font(.footnote)
                }
            }
            .navigationTitle("Application profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(saving ? "Saving…" : "Save") { Task { await save() } }
                        .disabled(saving)
                }
            }
            .onAppear(perform: load)
        }
    }

    /// A plain Form row, the same shape as the Cloudflare fields in Settings.
    ///
    /// Two earlier attempts here looked right and could not be typed into: a
    /// `LabeledContent` wrapper (that view is for displaying a value, and swallows
    /// the field's taps) and a `Text` + `TextField` HStack (the field never took
    /// focus anywhere along the row). The label doubles as the placeholder, which
    /// is what the rest of this Form already does — and it demonstrably works.
    @ViewBuilder
    private func field(_ key: String, _ label: String,
                       keyboard: UIKeyboardType = .default) -> some View {
        TextField(label, text: Binding(
            get: { f[key] ?? "" },
            set: { f[key] = $0 }
        ))
        .keyboardType(keyboard)
        .textInputAutocapitalization(keyboard == .emailAddress || keyboard == .URL ? .never : .sentences)
        .autocorrectionDisabled(keyboard == .emailAddress || keyboard == .URL)
    }

    /// Yes / No / unset. An unanswered work-authorization question is a real
    /// state, and it must not collapse into "No".
    @ViewBuilder
    private func tristate(_ label: String, _ value: Binding<Bool?>) -> some View {
        Picker(label, selection: Binding(
            get: { value.wrappedValue.map { $0 ? 1 : 0 } ?? -1 },
            set: { value.wrappedValue = $0 == -1 ? nil : ($0 == 1) }
        )) {
            Text("—").tag(-1)
            Text("No").tag(0)
            Text("Yes").tag(1)
        }
        .pickerStyle(.menu)
    }

    private func load() {
        let p = store.autofillProfile
        for k in Self.textKeys { f[k] = p[k] ?? "" }
        workAuthorized = flag(p["work_authorized"])
        requiresSponsorship = flag(p["requires_sponsorship"])
        willingToRelocate = flag(p["willing_to_relocate"])
    }

    /// The server hands these back as bools, but `autofillProfile` is flattened
    /// to strings on the way in, so both spellings have to be understood.
    private func flag(_ raw: String?) -> Bool? {
        guard let raw, !raw.isEmpty else { return nil }
        return ["true", "yes", "1"].contains(raw.lowercased())
    }

    private func save() async {
        saving = true
        defer { saving = false }
        var body: [String: Any] = [:]
        for k in Self.textKeys {
            let v = (f[k] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if !v.isEmpty { body[k] = v }
        }
        if let workAuthorized { body["work_authorized"] = workAuthorized }
        if let requiresSponsorship { body["requires_sponsorship"] = requiresSponsorship }
        if let willingToRelocate { body["willing_to_relocate"] = willingToRelocate }

        if let err = await store.saveAutofillProfile(body) {
            error = err
        } else {
            dismiss()
        }
    }
}
