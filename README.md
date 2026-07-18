# Luminate Installer

Luminate Installer is an elegant package conversion and installation desktop utility. It provides a modern GUI to convert Debian packages (`.deb`), AppImages, and other formats into Arch Linux native packages and install them seamlessly.

![Luminate Installer Logo](luminate-installer.svg)

## Features
- **Intuitive GUI**: Built with a responsive HTML/CSS/JS frontend served locally and rendered via `pywebview`.
- **Automatic Dependency Sanitization**: Automatically matches, sanitizes, and maps Debian package dependencies to their Arch Linux equivalents.
- **Robust Background Processing**: Handles downloads, extractions, and conversions in background worker threads without freezing the UI.
- **Wayland Compatibility**: Includes built-in stability fixes for Wayland-based GNOME desktop environments to prevent common WebKitGTK/DMA-BUF rendering crashes.

---

## Installation

### 1. Install on Arch Linux (via Pacman)

To install the package using the custom `pacman` repository:

1. Add the custom repository to your `/etc/pacman.conf`:
   ```ini
   [custom]
   SigLevel = Optional TrustAll
   Server = file:///home/custompkgs
   ```
2. Sync the databases and install:
   ```bash
   sudo pacman -Sy luminate-installer
   ```

### 2. Install on Debian/Ubuntu (via APT)

To install the package using the custom `APT` repository:

1. Add the repository to your `/etc/apt/sources.list.d/luminate.list`:
   ```text
   deb [trusted=yes] file:///home/aptpkgs ./
   ```
2. Update package lists and install:
   ```bash
   sudo apt update
   sudo apt install luminate-installer
   ```

---

## Running the Application
Simply run the launcher command from your terminal:
```bash
luminate-installer
```

---

## Contributors
- **[manuety](https://github.com/manuety)** — Original Author & Developer
- **[Google Antigravity](https://github.com/google-antigravity)** — AI Pair Programmer (Wayland stability patches, PKGBUILD setups, and Debian packaging)
