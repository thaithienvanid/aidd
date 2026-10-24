# Desktop distribution: the channels

Load this when a Spec picks or adds a release channel for a macOS, Windows, or Linux app. Name every channel the release uses in the Spec. Each has its own signing, review, and update path, and one build rarely serves two of them unchanged.

| Channel | Signing | Review | Updates |
| --- | --- | --- | --- |
| macOS, direct download | Developer ID certificate, hardened runtime, notarized, ticket stapled to the app, DMG, or PKG | none by a person; the notary service scans each upload | the app's own updater, signed (Sparkle, Electron's updater, or the Tauri updater) |
| Mac App Store | Apple distribution signing through Xcode; sandboxed | App Review, guideline 2.4.5 on top of the rest | the Mac App Store only; no other update mechanism |
| Windows, direct download | Authenticode on every PE file and the installer, timestamped, a certificate chained to the Microsoft Trusted Root Program | none | the app's own updater, signed and verified before install |
| Microsoft Store, MSIX | signed by the Store at ingestion | certification against the Microsoft Store Policies | the Store |
| Microsoft Store, MSI or EXE by URL (10.2.9) | the same Authenticode rule as direct download | certification; the versioned URL's binary must not change after submission | a new versioned URL in Partner Center for each release; an in-app updater must stay within 10.2.2 |
| Package managers (winget, a Homebrew cask) | the signed direct download | the repository's own pull-request review | a manifest per release, pinned to the download's SHA-256 |
| Steam | what each OS needs to launch the build | Valve reviews the store presence and the build before release | Steam; the app's own updater stays off |
| Linux, Flathub | the Flatpak repository's signature, which Flathub adds | a submission pull request on GitHub, reviewed by Flathub | Flathub builds and ships each release; the app's own updater stays off |
| Linux, direct download (AppImage or a tarball) | a detached signature, made with a key outside the repository, next to each download | none | the app's own updater, signed and verified before install |
| Linux, a distribution's repository or a package repository of your own | the repository's signed metadata | the distribution's own review, or none for your own repository | the system's package manager |

## Choosing

- A direct download is the only channel with no store review, so signing and the updater carry all the trust there. The updater checks a signature made with a key outside the repository, never only TLS.
- The Mac App Store's sandbox and update rules (2.4.5) exclude a self-updater, a license screen, and root escalation. A build for both channels turns these off by a build flag, tested in each channel.
- The Microsoft Store by URL keeps the existing installer but adds certification to every release.

## Signing keys

- A public code-signing certificate issued from 2026-03-01 lasts at most 460 days (CA/Browser Forum ballot CSC-31), so renewal is a yearly task with an owner. A timestamp keeps each signature valid after its certificate expires.
- The Developer ID and Authenticode keys live in a hardware module or a cloud signing service. They are never in the repository or in a CI variable in plain text. CI signs through the module or the service.
- The updater's key pair is separate from the platform signing keys. Its loss means shipping a new key through the platform-signed channel, so the rotation is written down before the first release.
