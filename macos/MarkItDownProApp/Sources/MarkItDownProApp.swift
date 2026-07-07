import AppKit
import SwiftUI
import UniformTypeIdentifiers

@main
struct MarkItDownProApp: App {
    @StateObject private var settings = AppSettings()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(settings)
                .frame(width: 560, height: 420)
        }
        .windowStyle(.titleBar)
        .defaultSize(width: 560, height: 420)
    }
}

final class AppSettings: ObservableObject {
    @Published var outputFolder: String {
        didSet { UserDefaults.standard.set(outputFolder, forKey: "outputFolder") }
    }
    @Published var modelFolder: String {
        didSet { UserDefaults.standard.set(modelFolder, forKey: "modelFolder") }
    }
    @Published var commandPath: String {
        didSet { UserDefaults.standard.set(commandPath, forKey: "commandPath") }
    }
    @Published var enableFormulaOCR: Bool {
        didSet { UserDefaults.standard.set(enableFormulaOCR, forKey: "enableFormulaOCR") }
    }

    init() {
        let downloads = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Downloads")
        let defaultOutput = downloads.appendingPathComponent("markitdown-output").path
        let defaultModel = "/Users/wudong/Code/Tools/markitdownpro/.cache"
        let defaultCommand = "/Users/wudong/Code/Tools/markitdownpro/.venv/bin/markitdownpro"

        let savedOutput = UserDefaults.standard.string(forKey: "outputFolder")
        outputFolder = savedOutput?.hasSuffix("/maritdown-output") == true ? defaultOutput : (savedOutput ?? defaultOutput)
        let savedModel = UserDefaults.standard.string(forKey: "modelFolder")
        modelFolder = savedModel?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false ? savedModel! : defaultModel
        commandPath = UserDefaults.standard.string(forKey: "commandPath") ?? defaultCommand
        enableFormulaOCR = UserDefaults.standard.object(forKey: "enableFormulaOCR") as? Bool ?? true
    }
}

struct ProgressEvent: Decodable {
    let stage: String
    let current: Int?
    let total: Int?
    let message: String?
}

@MainActor
final class ConversionModel: ObservableObject {
    enum State: Equatable {
        case idle
        case running
        case succeeded
        case failed
    }

    @Published var selectedFile: URL?
    @Published var state: State = .idle
    @Published var progress: Double = 0
    @Published var elapsedSeconds: TimeInterval = 0
    @Published var progressMessage = "等待文件"
    @Published var outputText = ""
    @Published var outputPath: String?
    @Published var errorMessage: String?

    private var process: Process?
    private var timer: Timer?
    private var startedAt: Date?

    var isRunning: Bool {
        state == .running
    }

    func selectFile(_ url: URL, settings: AppSettings) {
        guard !isRunning else { return }
        selectedFile = url
        start(settings: settings)
    }

    func start(settings: AppSettings) {
        guard let selectedFile, !isRunning else { return }

        state = .running
        progress = 0
        elapsedSeconds = 0
        progressMessage = "正在准备转换"
        outputText = ""
        outputPath = nil
        errorMessage = nil
        startedAt = Date()

        let outputFolder = URL(fileURLWithPath: settings.outputFolder)
        do {
            try FileManager.default.createDirectory(
                at: outputFolder,
                withIntermediateDirectories: true
            )
        } catch {
            fail("无法创建输出目录：\(error.localizedDescription)")
            return
        }

        let executable = URL(fileURLWithPath: settings.commandPath)
        let process = Process()
        process.executableURL = executable
        var arguments = [
            selectedFile.path,
            "-o",
            outputFolder.path,
            "--progress",
        ]
        if !settings.enableFormulaOCR {
            arguments.append("--no-pdf-formula-ocr")
        }
        process.arguments = arguments

        var environment = ProcessInfo.processInfo.environment
        if !settings.modelFolder.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            environment["MARKITDOWNPRO_CACHE_DIR"] = settings.modelFolder
        }
        process.environment = environment

        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr
        self.process = process

        stdout.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor in
                self?.appendOutput(text)
            }
        }
        stderr.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor in
                self?.appendOutput(text)
            }
        }

        process.terminationHandler = { [weak self] process in
            stdout.fileHandleForReading.readabilityHandler = nil
            stderr.fileHandleForReading.readabilityHandler = nil
            Task { @MainActor in
                self?.finish(exitCode: process.terminationStatus)
            }
        }

        do {
            try process.run()
            startTimer()
        } catch {
            fail("无法启动转换命令：\(error.localizedDescription)")
        }
    }

    func cancel() {
        guard isRunning else { return }
        process?.terminate()
        fail("已取消转换。")
    }

    private func appendOutput(_ text: String) {
        let lines = text.split(whereSeparator: \.isNewline).map(String.init)
        var visibleLines: [String] = []
        for line in lines {
            if line.hasPrefix("MARKITDOWNPRO_PROGRESS ") {
                handleProgressLine(line)
            } else {
                visibleLines.append(line)
            }
        }

        if !visibleLines.isEmpty {
            outputText += visibleLines.joined(separator: "\n") + "\n"
        }

        let allLines = outputText.split(whereSeparator: \.isNewline).map(String.init)
        if let path = allLines.last(where: { $0.hasSuffix(".md") }) {
            outputPath = path
        }
    }

    private func handleProgressLine(_ line: String) {
        let prefix = "MARKITDOWNPRO_PROGRESS "
        guard line.hasPrefix(prefix) else { return }
        let jsonText = String(line.dropFirst(prefix.count))
        guard let data = jsonText.data(using: .utf8),
              let event = try? JSONDecoder().decode(ProgressEvent.self, from: data)
        else { return }

        progressMessage = event.message ?? progressMessage
        switch event.stage {
        case "prepare":
            progress = max(progress, 0.03)
        case "pages":
            progress = max(progress, 0.05 + fraction(event) * 0.75)
        case "docx":
            progress = max(progress, 0.05 + fraction(event) * 0.35)
        case "images":
            progress = max(progress, 0.40 + fraction(event) * 0.35)
        case "markdown":
            progress = max(progress, 0.88)
        case "write":
            progress = max(progress, 0.95)
        case "done":
            progress = 1
        default:
            break
        }
    }

    private func fraction(_ event: ProgressEvent) -> Double {
        guard let current = event.current, let total = event.total, total > 0 else {
            return 0
        }
        return min(max(Double(current) / Double(total), 0), 1)
    }

    private func startTimer() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self, self.state == .running, let startedAt = self.startedAt else { return }
                self.elapsedSeconds = Date().timeIntervalSince(startedAt)
            }
        }
    }

    private func finish(exitCode: Int32) {
        timer?.invalidate()
        timer = nil
        process = nil
        elapsedSeconds = Date().timeIntervalSince(startedAt ?? Date())

        if exitCode == 0 {
            state = .succeeded
            progress = 1
            progressMessage = "转换完成"
            if outputPath == nil {
                outputPath = outputText
                    .split(whereSeparator: \.isNewline)
                    .map(String.init)
                    .last(where: { $0.hasSuffix(".md") })
            }
        } else {
            fail("转换失败，退出码：\(exitCode)")
        }
    }

    private func fail(_ message: String) {
        timer?.invalidate()
        timer = nil
        process = nil
        state = .failed
        errorMessage = message
        progressMessage = message
        progress = 0
    }
}

struct ContentView: View {
    @EnvironmentObject private var settings: AppSettings
    @StateObject private var model = ConversionModel()
    @State private var isTargeted = false
    @State private var showingSettings = false
    @State private var showingLog = false

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            VStack(spacing: 12) {
                dropZone
                statusPanel
                outputPanel
            }
            .padding(.horizontal, 18)
            .padding(.bottom, 16)
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .sheet(isPresented: $showingSettings) {
            SettingsView()
                .environmentObject(settings)
        }
    }

    private var toolbar: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("MarkItDownPro")
                    .font(.system(size: 17, weight: .semibold))
                Text("PDF / DOCX 转 Markdown")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()

            Toggle("公式 OCR", isOn: $settings.enableFormulaOCR)
                .toggleStyle(.switch)
                .disabled(model.isRunning)

            Button {
                showingSettings = true
            } label: {
                Image(systemName: "gearshape")
            }
            .buttonStyle(.bordered)
            .help("设置模型和输出路径")
        }
        .padding(.horizontal, 18)
        .padding(.top, 14)
        .padding(.bottom, 10)
    }

    private var dropZone: some View {
        HStack(spacing: 14) {
            ZStack {
                Circle()
                    .fill(isTargeted ? Color.accentColor.opacity(0.15) : Color.secondary.opacity(0.10))
                    .frame(width: 54, height: 54)
                Image(systemName: model.isRunning ? "arrow.triangle.2.circlepath" : "doc.badge.plus")
                    .font(.system(size: 25, weight: .medium))
                    .foregroundStyle(isTargeted ? Color.accentColor : Color.secondary)
            }

            VStack(alignment: .leading, spacing: 5) {
                Text(model.selectedFile?.lastPathComponent ?? "拖拽 PDF 或 DOCX 到这里")
                    .font(.system(size: 16, weight: .semibold))
                    .lineLimit(2)
                Text(model.selectedFile == nil ? "点击选择文件后会立即开始处理。" : "文件已载入，正在准备转换。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer(minLength: 8)

            VStack(spacing: 8) {
                Button {
                    pickFile()
                } label: {
                    Label("选择文件", systemImage: "folder")
                }
                .disabled(model.isRunning)
                .controlSize(.regular)

                if model.isRunning {
                    Button(role: .cancel) {
                        model.cancel()
                    } label: {
                        Label("取消", systemImage: "xmark")
                    }
                    .controlSize(.small)
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, minHeight: 116)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isTargeted ? Color.accentColor.opacity(0.10) : Color(nsColor: .controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isTargeted ? Color.accentColor : Color.secondary.opacity(0.25), lineWidth: 1)
        )
        .onDrop(of: [.fileURL], isTargeted: $isTargeted) { providers in
            guard !model.isRunning else { return false }
            guard let provider = providers.first else { return false }
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
                guard let data = item as? Data,
                      let url = URL(dataRepresentation: data, relativeTo: nil)
                else { return }
                Task { @MainActor in
                    model.selectFile(url, settings: settings)
                }
            }
            return true
        }
    }

    private var statusPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(statusText)
                    .font(.system(size: 14, weight: .semibold))
                Spacer()
                Text(timeText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }
            ProgressView(value: model.progress)
                .progressViewStyle(.linear)
            if let error = model.errorMessage {
                Text(error)
                    .foregroundStyle(.red)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
    }

    private var outputPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("输出")
                    .font(.system(size: 14, weight: .semibold))
                Spacer()
                Button {
                    openOutputFolder()
                } label: {
                    Label("打开输出文件夹", systemImage: "arrow.up.forward.app")
                }
            }
            Text(model.outputPath ?? settings.outputFolder)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
                .textSelection(.enabled)
            DisclosureGroup("命令行输出", isExpanded: $showingLog) {
                ScrollView {
                    Text(model.outputText.isEmpty ? "转换日志会显示在这里。" : model.outputText)
                        .font(.system(.caption, design: .monospaced))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .textSelection(.enabled)
                }
                .frame(minHeight: 95)
                .padding(10)
                .background(Color(nsColor: .textBackgroundColor))
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.secondary.opacity(0.2))
                )
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
    }

    private var statusText: String {
        switch model.state {
        case .idle:
            return "等待文件"
        case .running:
            return model.progressMessage
        case .succeeded:
            return "转换完成"
        case .failed:
            return "转换失败"
        }
    }

    private var timeText: String {
        if model.state == .running {
            return "已用 \(format(model.elapsedSeconds))"
        }
        if model.elapsedSeconds > 0 {
            return "耗时 \(format(model.elapsedSeconds))"
        }
        return ""
    }

    private func pickFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [
            UTType(filenameExtension: "pdf")!,
            UTType(filenameExtension: "docx")!,
        ]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        if panel.runModal() == .OK, let url = panel.url {
            model.selectFile(url, settings: settings)
        }
    }

    private func openOutputFolder() {
        NSWorkspace.shared.open(URL(fileURLWithPath: settings.outputFolder))
    }

    private func format(_ seconds: TimeInterval) -> String {
        let seconds = max(0, Int(seconds.rounded()))
        let minutes = seconds / 60
        let remaining = seconds % 60
        if minutes > 0 {
            return "\(minutes)m \(remaining)s"
        }
        return "\(remaining)s"
    }
}

struct SettingsView: View {
    @EnvironmentObject private var settings: AppSettings
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Text("设置")
                    .font(.system(size: 19, weight: .semibold))
                Spacer()
                Button("完成") {
                    dismiss()
                }
                .keyboardShortcut(.defaultAction)
            }

            settingRow(
                title: "模型文件夹",
                subtitle: "对应 MARKITDOWNPRO_CACHE_DIR，默认使用项目内 .cache。模型不会打包进应用。",
                value: $settings.modelFolder,
                chooseDirectory: true
            )

            settingRow(
                title: "输出文件夹",
                subtitle: "默认是下载文件夹中的 markitdown-output。",
                value: $settings.outputFolder,
                chooseDirectory: true
            )

            settingRow(
                title: "转换命令",
                subtitle: "默认使用当前项目虚拟环境中的 markitdownpro。",
                value: $settings.commandPath,
                chooseDirectory: false
            )
        }
        .padding(22)
        .frame(width: 560)
    }

    private func settingRow(
        title: String,
        subtitle: String,
        value: Binding<String>,
        chooseDirectory: Bool
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.system(size: 14, weight: .semibold))
            Text(subtitle)
                .foregroundStyle(.secondary)
                .font(.caption)
            HStack {
                TextField("", text: value)
                    .textFieldStyle(.roundedBorder)
                Button("选择") {
                    choose(value: value, directory: chooseDirectory)
                }
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
    }

    private func choose(value: Binding<String>, directory: Bool) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = directory
        panel.canChooseFiles = !directory
        panel.canCreateDirectories = directory
        panel.showsHiddenFiles = true
        if panel.runModal() == .OK, let url = panel.url {
            value.wrappedValue = url.path
        }
    }
}
