import SwiftUI
import UIKit
import CoreText

/// Renders a title + body string into a clean, paginated US-Letter PDF.
enum PDFExport {
    static func render(title: String, body: String) -> URL? {
        let pageW: CGFloat = 612, pageH: CGFloat = 792   // US Letter @ 72dpi
        let margin: CGFloat = 56
        let renderer = UIGraphicsPDFRenderer(bounds: CGRect(x: 0, y: 0, width: pageW, height: pageH))

        let titleAttr: [NSAttributedString.Key: Any] = [
            .font: UIFont.systemFont(ofSize: 18, weight: .semibold), .foregroundColor: UIColor.black]
        let bodyPara = NSMutableParagraphStyle(); bodyPara.lineSpacing = 3.5
        let bodyAttr: [NSAttributedString.Key: Any] = [
            .font: UIFont.systemFont(ofSize: 11), .foregroundColor: UIColor.black, .paragraphStyle: bodyPara]

        let full = NSMutableAttributedString(string: title + "\n\n", attributes: titleAttr)
        full.append(NSAttributedString(string: body, attributes: bodyAttr))

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent(safeName(title) + ".pdf")
        do {
            try renderer.writePDF(to: url) { ctx in
                let framesetter = CTFramesetterCreateWithAttributedString(full)
                var cursor = 0
                let textRect = CGRect(x: margin, y: margin, width: pageW - margin * 2, height: pageH - margin * 2)
                while cursor < full.length {
                    ctx.beginPage()
                    let cg = ctx.cgContext
                    cg.textMatrix = .identity
                    cg.translateBy(x: 0, y: pageH)
                    cg.scaleBy(x: 1, y: -1)
                    let path = CGPath(rect: textRect, transform: nil)
                    let frame = CTFramesetterCreateFrame(framesetter, CFRange(location: cursor, length: 0), path, nil)
                    CTFrameDraw(frame, cg)
                    let visible = CTFrameGetVisibleStringRange(frame)
                    if visible.length == 0 { break }   // guard against a no-progress loop
                    cursor += visible.length
                }
            }
            return url
        } catch { return nil }
    }

    private static func safeName(_ s: String) -> String {
        let cleaned = s.components(separatedBy: CharacterSet(charactersIn: "/\\:?%*|\"<>")).joined(separator: "-")
        let trimmed = cleaned.trimmingCharacters(in: .whitespaces)
        return trimmed.isEmpty ? "Recon document" : String(trimmed.prefix(80))
    }
}

/// UIActivityViewController bridge for sharing a file URL.
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}

/// Drop-in "Export PDF" button: renders `title`/`body` to a PDF and opens the share sheet.
struct ExportPDFButton: View {
    let title: String
    let body: String
    var label: String = "Export PDF"
    var soft: Bool = true
    @State private var shareURL: URL?
    @State private var showShare = false

    var body: some View {
        Button {
            if let url = PDFExport.render(title: title, body: body) {
                shareURL = url; showShare = true
            }
        } label: { Label(label, systemImage: "square.and.arrow.up") }
        .buttonStyle(ReconButtonStyle(color: Theme.rust, soft: soft))
        .sheet(isPresented: $showShare) {
            if let url = shareURL { ShareSheet(items: [url]) }
        }
    }
}
