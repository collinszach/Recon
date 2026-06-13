import SwiftUI

struct SettingsView: View {
    @StateObject private var config = AppConfig.shared
    @Environment(\.dismiss) private var dismiss
    let onApply: () -> Void

    var body: some View {
        NavigationStack {
            Form {
                Section("Server") {
                    Picker("Connect via", selection: $config.endpoint) {
                        ForEach(Endpoint.allCases) { Text($0.label).tag($0) }
                    }
                    if config.endpoint == .custom {
                        TextField("https://host:port", text: $config.customURL)
                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                            .keyboardType(.URL)
                    }
                    LabeledContent("Active URL") {
                        Text(config.baseURL.absoluteString).font(.footnote.monospaced())
                            .foregroundStyle(.secondary)
                    }
                }

                Section("Cloudflare Access (service token)") {
                    TextField("CF-Access-Client-Id", text: $config.cfAccessId)
                        .textInputAutocapitalization(.never).autocorrectionDisabled().font(.footnote.monospaced())
                    SecureField("CF-Access-Client-Secret", text: $config.cfAccessSecret)
                        .font(.footnote.monospaced())
                    Text("Only needed for the Tunnel endpoint once an Access policy is enforced. Create a service token in Zero Trust → Access → Service Auth and add it to the Recon application's policy. The Local (Tailscale) endpoint bypasses Access and needs nothing here.")
                        .font(.footnote).foregroundStyle(.secondary)
                }

                Section {
                    Text("Tunnel works anywhere. Local works on your home network or with Tailscale connected.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { onApply(); dismiss() }
                }
            }
        }
    }
}
