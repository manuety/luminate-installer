#!/bin/bash
set -e

echo "=== Luminate Installer Setup ==="
echo "This script will clone, build, and install Luminate Installer on your system."

# Check if pacman is available
if ! command -v pacman &> /dev/null; then
    echo "Error: pacman package manager not found. This installer only supports Arch Linux-based systems."
    exit 1
fi

# Create temporary build directory
TMP_DIR=$(mktemp -d)
echo "Using temporary build directory: $TMP_DIR"

# Clean up on exit or error
trap 'rm -rf "$TMP_DIR"' EXIT

# Clone the repository
echo "Cloning the repository..."
git clone https://github.com/manuety/luminate-installer.git "$TMP_DIR"

# Build and install using makepkg
echo "Building and installing the package..."
cd "$TMP_DIR"
makepkg -si --noconfirm

echo "=== Installation Complete! ==="
echo "You can now run the app using the command: luminate-installer"
