// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "MarkItDownProApp",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "MarkItDownProApp", targets: ["MarkItDownProApp"])
    ],
    targets: [
        .executableTarget(
            name: "MarkItDownProApp",
            path: "Sources"
        )
    ]
)
