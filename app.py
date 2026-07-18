import os
import sys
import json
import uuid
import shutil
import threading
import subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse

# Setup paths
USER_DATA_DIR = Path.home() / ".local" / "share" / "luminate-installer"
UPLOAD_DIR = USER_DATA_DIR / "uploads"
CONVERTED_DIR = USER_DATA_DIR / "converted"
STATIC_DIR = Path(__file__).parent.resolve() / "static"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CONVERTED_DIR.mkdir(parents=True, exist_ok=True)

# Task tracking
tasks = {}

def log_write(task, text):
    """Append text to task logs and write to ~/luminate/<filename>.log."""
    task["logs"].append(text)
    try:
        log_dir = Path.home() / "luminate"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{task['filename']}.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass

def is_valid_arch_package(name):
    try:
        ret = subprocess.run(
            ["pacman", "-Si", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2
        )
        if ret.returncode == 0:
            return True
    except Exception:
        pass
        
    try:
        ret = subprocess.run(
            ["yay", "-Si", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3
        )
        if ret.returncode == 0:
            return True
    except Exception:
        pass
        
    return False

def clean_dependency(dep):
    dep = dep.strip()
    
    if dep == "c":
        return "glibc"
        
    # If package name is already valid, do not sanitize
    if is_valid_arch_package(dep):
        return dep
        
    for op in (">=", "<=", "=", ">", "<"):
        if op in dep:
            name = dep.split(op)[0].strip()
            if name == "c":
                name = "glibc"
            if is_valid_arch_package(name):
                return name
            return name
            
    dot_idx = dep.find(".")
    if dot_idx != -1:
        ver_start = dot_idx - 1
        if ver_start >= 0 and dep[ver_start].isdigit():
            name = dep[:ver_start].strip()
            name = name.rstrip("-")
            if name == "c":
                name = "glibc"
            if is_valid_arch_package(name):
                return name
            return name

    if dep == "c":
        return "glibc"
    return dep

def sanitize_package_metadata(pkg_path, task):
    pkg_path = Path(pkg_path).resolve()
    if not pkg_path.exists():
        log_write(task, f"Sanitization error: package path {pkg_path} does not exist.\n")
        return False
        
    log_write(task, "Extracting package for dependency sanitization...\n")
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        try:
            subprocess.run(
                ["tar", "-xf", str(pkg_path), "-C", str(tmpdir_path)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        except Exception as e:
            log_write(task, f"Sanitization error during extraction: {e}\n")
            return False
            
        pkginfo_path = tmpdir_path / ".PKGINFO"
        if not pkginfo_path.exists():
            log_write(task, "Sanitization error: .PKGINFO not found in extracted archive.\n")
            return False
            
        # Read and modify .PKGINFO
        lines = pkginfo_path.read_text(encoding="utf-8").splitlines()
        new_lines = []
        modified = False
        seen_deps = set()
        for line in lines:
            if line.startswith("depend = "):
                dep = line.split("=", 1)[1].strip()
                cleaned_dep = clean_dependency(dep)
                if cleaned_dep != dep:
                    log_write(task, f"  Sanitized dependency: '{dep}' -> '{cleaned_dep}'\n")
                    modified = True
                if cleaned_dep and cleaned_dep not in seen_deps:
                    seen_deps.add(cleaned_dep)
                    new_lines.append(f"depend = {cleaned_dep}")
            else:
                new_lines.append(line)
                
        if modified:
            pkginfo_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            log_write(task, "Repacking sanitized package...\n")
            try:
                pkg_path.unlink()
                # Repack using tar -I zstd
                files_to_pack = [f.name for f in tmpdir_path.iterdir()]
                subprocess.run(
                    ["tar", "-I", "zstd", "-cf", str(pkg_path)] + files_to_pack,
                    cwd=str(tmpdir_path),
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                log_write(task, "Package dependencies successfully sanitized!\n")
            except Exception as e:
                log_write(task, f"Sanitization error during repacking: {e}\n")
                return False
        else:
            log_write(task, "No dependencies needed sanitization.\n")
            
    return True

def parse_context_and_progress(line, task, file_ext):
    line_lower = line.lower()
    sub_progress = 0
    context = ""
    
    # Matches for Debtap conversion stages
    if "synchronizing pkgfile" in line_lower:
        context = "Synchronizing system file database..."
        sub_progress = 5
    elif "synchronizing debtap" in line_lower:
        context = "Synchronizing Debtap package index..."
        sub_progress = 10
    elif "downloading latest virtual packages" in line_lower:
        context = "Downloading virtual package maps..."
        sub_progress = 15
    elif "generating extended base group" in line_lower:
        context = "Generating dependency groups..."
        sub_progress = 20
    elif "making package:" in line_lower:
        context = "Building package archive..."
        sub_progress = 25
    elif "checking runtime dependencies" in line_lower:
        context = "Analyzing runtime dependencies..."
        sub_progress = 30
    elif "checking buildtime dependencies" in line_lower:
        context = "Analyzing build dependencies..."
        sub_progress = 35
    elif "retrieving sources" in line_lower:
        context = "Retrieving package source files..."
        sub_progress = 40
    elif "extracting sources" in line_lower:
        context = "Unpacking package binaries..."
        sub_progress = 50
    elif "starting package()" in line_lower:
        context = "Converting directory layout to Arch..."
        sub_progress = 65
    elif "tidying install" in line_lower:
        context = "Optimizing package file paths..."
        sub_progress = 75
    elif "checking for packaging issues" in line_lower:
        context = "Running package diagnostics..."
        sub_progress = 85
    elif "creating package" in line_lower:
        context = "Compressing binaries into .pkg.tar.zst..."
        sub_progress = 90
    elif "generating .pkginfo" in line_lower or "generating .mtree" in line_lower:
        context = "Writing package metadata..."
        sub_progress = 95
        
    # Matches for Pacman installation stages
    elif "loading packages" in line_lower:
        context = "Loading metadata..."
        sub_progress = 10
    elif "resolving dependencies" in line_lower:
        context = "Resolving system dependencies..."
        sub_progress = 20
    elif "checking keys in keyring" in line_lower:
        context = "Verifying package signature keys..."
        sub_progress = 30
    elif "checking package integrity" in line_lower:
        context = "Verifying package integrity..."
        sub_progress = 40
    elif "checking for file conflicts" in line_lower:
        context = "Checking for file conflicts..."
        sub_progress = 50
    elif "installing " in line_lower:
        pkg = line.split("installing")[-1].strip().split()[0]
        context = f"Installing package {pkg}..."
        sub_progress = 70
    elif "running post-transaction hooks" in line_lower:
        context = "Running post-install hooks..."
        sub_progress = 85
    elif "updating the desktop file mime type cache" in line_lower:
        context = "Registering system launchers..."
        sub_progress = 95
    elif "arm conditionneedsupdate" in line_lower:
        context = "Updating system caches..."
        sub_progress = 98
        
    if context:
        task["context"] = context
        
    if sub_progress > 0:
        if task["status"] == "converting":
            task["progress"] = max(task["progress"], int(sub_progress * 0.5))
        elif task["status"] == "installing":
            if file_ext == "deb":
                task["progress"] = max(task["progress"], 50 + int(sub_progress * 0.48))
            else:
                task["progress"] = max(task["progress"], int(sub_progress * 0.98))

def run_cmd_log(cmd, task_id, cwd=None):
    """Run a subprocess and stream its stdout/stderr to task logs."""
    task = tasks[task_id]
    file_ext = task["filename"].split(".")[-1].lower()
    log_write(task, f"$ {' '.join(cmd)}\n")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=cwd
        )
        task["proc"] = proc
        
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                log_write(task, line)
                parse_context_and_progress(line, task, file_ext)
        
        proc.wait()
        return proc.returncode
    except Exception as e:
        log_write(task, f"Subprocess execution failed: {e}\n")
        return -1

def get_appimage_info(appimage_path, app_id):
    """Try to extract desktop file and icon from AppImage."""
    extract_dir = UPLOAD_DIR / f"extract_{app_id}"
    extract_dir.mkdir(parents=True, exist_ok=True)
    
    # Run AppImage extraction
    cmd = [str(appimage_path), "--appimage-extract"]
    # We must run it inside extract_dir
    try:
        subprocess.run(cmd, cwd=extract_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        squashfs = extract_dir / "squashfs-root"
        if squashfs.exists():
            # Find .desktop file
            desktop_files = list(squashfs.glob("*.desktop"))
            icon_files = list(squashfs.glob("*.png")) + list(squashfs.glob("*.svg"))
            
            desktop_content = ""
            icon_name = "system-run"
            
            if desktop_files:
                desktop_content = desktop_files[0].read_text(errors="ignore")
            
            if icon_files:
                # Copy icon to ~/.local/share/icons/
                icons_dest = Path.home() / ".local" / "share" / "icons"
                icons_dest.mkdir(parents=True, exist_ok=True)
                icon_file = icon_files[0]
                dest_icon_path = icons_dest / f"{app_id}{icon_file.suffix}"
                shutil.copy2(icon_file, dest_icon_path)
                icon_name = str(dest_icon_path)
                
            return desktop_content, icon_name
    except Exception as e:
        pass
    finally:
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)
            
    return "", "system-run"

def create_desktop_entry(app_name, exec_path, icon_path, orig_desktop_content=None):
    """Create a desktop entry for the installed AppImage/binary."""
    apps_dir = Path.home() / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    
    desktop_file = apps_dir / f"{app_name}.desktop"
    
    if orig_desktop_content:
        # Edit existing desktop file to point to our Exec and Icon
        lines = orig_desktop_content.splitlines()
        new_lines = []
        has_exec = False
        has_icon = False
        for line in lines:
            if line.startswith("Exec="):
                new_lines.append(f"Exec={exec_path}")
                has_exec = True
            elif line.startswith("Icon="):
                new_lines.append(f"Icon={icon_path}")
                has_icon = True
            else:
                new_lines.append(line)
        if not has_exec:
            new_lines.append(f"Exec={exec_path}")
        if not has_icon:
            new_lines.append(f"Icon={icon_path}")
        desktop_file.write_text("\n".join(new_lines))
    else:
        # Generate generic desktop file
        content = f"""[Desktop Entry]
Type=Application
Name={app_name.replace('-', ' ').title()}
Exec={exec_path}
Icon={icon_path}
Terminal=false
Categories=Utility;
"""
        desktop_file.write_text(content)

def install_task_worker(task_id, filepath, filename):
    task = tasks[task_id]
    suffix = filepath.suffix.lower()
    
    try:
        if suffix == ".deb":
            # 1. Conversion stage
            task["status"] = "converting"
            task["context"] = "Starting Debian package conversion..."
            log_write(task, f"Converting Debian package {filename} via debtap...\n")
            
            # Run debtap -Q -w
            cmd = ["debtap", "-Q", "-w", "-o", str(CONVERTED_DIR), str(filepath)]
            ret = run_cmd_log(cmd, task_id)
            
            if ret != 0:
                task["status"] = "failed"
                task["context"] = "Conversion failed."
                log_write(task, "Conversion failed.\n")
                return
                
            # Find the converted file in converted/
            converted_files = list(CONVERTED_DIR.glob("*.pkg.tar.zst")) + list(CONVERTED_DIR.glob("*.pkg.tar.xz"))
            # Get the newest one
            if not converted_files:
                task["status"] = "failed"
                task["context"] = "Converted package not found."
                log_write(task, "Error: Converted Arch package not found.\n")
                return
                
            converted_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            pkg_path = converted_files[0]
            
            # Sanitize package dependencies before installation
            task["context"] = "Sanitizing package dependencies..."
            sanitize_package_metadata(pkg_path, task)
            
            # 2. Installation stage
            task["status"] = "installing"
            task["context"] = "Starting Arch package installation..."
            log_write(task, f"Installing converted package {pkg_path.name}...\n")
            
            # Install package using yay -U (resolves dependencies)
            cmd = ["yay", "--sudo", "pkexec", "-U", "--noconfirm", str(pkg_path)]
            ret = run_cmd_log(cmd, task_id)
            
            if ret == 0:
                task["status"] = "completed"
                task["progress"] = 100
                task["context"] = "Successfully installed package!"
                log_write(task, "Successfully installed converted package!\n")
            else:
                task["status"] = "failed"
                task["context"] = "Installation failed."
                log_write(task, "Installation failed.\n")
                
        elif suffix in (".zst", ".xz") and filename.endswith(".pkg.tar.zst") or filename.endswith(".pkg.tar.xz"):
            # Direct arch package installation
            task["status"] = "installing"
            task["context"] = "Installing Arch package..."
            log_write(task, f"Installing Arch Linux package {filename}...\n")
            
            cmd = ["yay", "--sudo", "pkexec", "-U", "--noconfirm", str(filepath)]
            ret = run_cmd_log(cmd, task_id)
            
            if ret == 0:
                task["status"] = "completed"
                task["progress"] = 100
                task["context"] = "Successfully installed package!"
                log_write(task, "Successfully installed Arch package!\n")
            else:
                task["status"] = "failed"
                task["context"] = "Installation failed."
                log_write(task, "Installation failed.\n")
                
        elif suffix == ".appimage":
            # AppImage setup
            task["status"] = "installing"
            task["context"] = "Initializing AppImage installer..."
            task["progress"] = 15
            log_write(task, f"Processing AppImage {filename}...\n")
            
            # Set executable permission
            filepath.chmod(filepath.stat().st_mode | 0o111)
            
            # Make sure ~/.local/bin/ exists
            bin_dir = Path.home() / ".local" / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            
            app_id = filename.lower().replace(".appimage", "").replace(" ", "-")
            dest_path = bin_dir / app_id
            
            task["context"] = "Copying AppImage to local bin..."
            task["progress"] = 40
            log_write(task, f"Copying AppImage to {dest_path}...\n")
            shutil.copy2(filepath, dest_path)
            
            # Try to extract desktop file and icon
            task["context"] = "Extracting AppImage metadata..."
            task["progress"] = 65
            log_write(task, "Extracting AppImage metadata for desktop entry...\n")
            desktop_content, icon_path = get_appimage_info(dest_path, app_id)
            
            task["context"] = "Creating application launcher..."
            task["progress"] = 85
            log_write(task, "Creating application launcher...\n")
            create_desktop_entry(app_id, str(dest_path), icon_path, desktop_content)
            
            task["status"] = "completed"
            task["progress"] = 100
            task["context"] = "AppImage successfully installed!"
            log_write(task, "Successfully installed AppImage! It is now available in your launcher.\n")
            
        else:
            # Generic binary or archive
            task["status"] = "failed"
            task["context"] = "Unsupported file format."
            log_write(task, f"Unsupported file format: {suffix}\n")
            
    except Exception as e:
        task["status"] = "failed"
        task["context"] = f"Error: {e}"
        log_write(task, f"Worker thread error: {e}\n")
        
    finally:
        # Cleanup uploaded file
        if filepath.exists():
            try:
                filepath.unlink()
            except Exception:
                pass

# Custom HTTP Request Handler
class LuminateHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence HTTP log messages in stdout
        pass

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        # API endpoints
        if path == "/api/status":
            # Check system info
            is_arch = Path("/etc/arch-release").exists() or Path("/usr/bin/pacman").exists()
            debtap_installed = shutil.which("debtap") is not None
            
            self.send_json({
                "arch": is_arch,
                "debtap": debtap_installed,
                "server_running": True
            })
            return
            
        elif path.startswith("/api/task/"):
            task_id = path.split("/")[-1]
            if task_id in tasks:
                t = tasks[task_id]
                self.send_json({
                    "id": task_id,
                    "status": t["status"],
                    "filename": t["filename"],
                    "progress": t["progress"],
                    "context": t.get("context", ""),
                    "logs": "".join(t["logs"])
                })
            else:
                self.send_json({"error": "Task not found"}, 404)
            return

        # Serve static frontend
        if path == "/":
            path = "/index.html"
            
        file_path = STATIC_DIR / path.lstrip("/")
        
        # Security check: ensure path is under static dir
        try:
            resolved_path = file_path.resolve()
            if not str(resolved_path).startswith(str(STATIC_DIR.resolve())):
                self.send_response(403)
                self.end_headers()
                return
        except Exception:
            self.send_response(404)
            self.end_headers()
            return
            
        if file_path.exists() and file_path.is_file():
            self.send_response(200)
            # Determine content type
            if file_path.suffix == ".html":
                self.send_header("Content-Type", "text/html")
            elif file_path.suffix == ".css":
                self.send_header("Content-Type", "text/css")
            elif file_path.suffix == ".js":
                self.send_header("Content-Type", "application/javascript")
            elif file_path.suffix == ".svg":
                self.send_header("Content-Type", "image/svg+xml")
            elif file_path.suffix == ".png":
                self.send_header("Content-Type", "image/png")
            self.end_headers()
            with open(file_path, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        if path == "/api/upload":
            content_type = self.headers.get("Content-Type")
            if not content_type or not content_type.startswith("multipart/form-data"):
                self.send_json({"error": "Content-Type must be multipart/form-data"}, 400)
                return
                
            boundary = content_type.split("boundary=")[1].encode()
            content_length = int(self.headers.get("Content-Length", 0))
            
            if content_length == 0:
                self.send_json({"error": "Content length is 0"}, 400)
                return
                
            # Read all body bytes
            body = self.rfile.read(content_length)
            
            # Simple multipart parser
            parts = body.split(b"--" + boundary)
            file_data = None
            filename = None
            
            for part in parts:
                if b"Content-Disposition" in part:
                    headers_part, data_part = part.split(b"\r\n\r\n", 1)
                    headers_text = headers_part.decode("utf-8", errors="ignore")
                    
                    if 'name="file"' in headers_text:
                        # Extract filename
                        for line in headers_text.split("\r\n"):
                            if "filename=" in line:
                                filename = line.split("filename=")[1].strip('"')
                                break
                        # Strip trailing \r\n from data_part
                        if data_part.endswith(b"\r\n"):
                            data_part = data_part[:-2]
                        file_data = data_part
                        break
            
            if not filename or file_data is None:
                self.send_json({"error": "File not found in multipart body"}, 400)
                return
                
            # Save uploaded file
            save_path = UPLOAD_DIR / filename
            with open(save_path, "wb") as f:
                f.write(file_data)
                
            # Create a background task
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            tasks[task_id] = {
                "status": "idle",
                "filename": filename,
                "progress": 0,
                "context": "File uploaded successfully.",
                "logs": [f"File {filename} uploaded successfully. Ready to process.\n"],
                "proc": None
            }
            
            # Start worker thread
            thread = threading.Thread(
                target=install_task_worker,
                args=(task_id, save_path, filename)
            )
            thread.daemon = True
            thread.start()
            
            self.send_json({
                "success": True,
                "task_id": task_id,
                "filename": filename
            })
            return
            
        elif path.startswith("/api/cancel/"):
            task_id = path.split("/")[-1]
            if task_id in tasks:
                t = tasks[task_id]
                if t["status"] in ("converting", "installing") and t["proc"]:
                    try:
                        t["proc"].terminate()
                        t["status"] = "failed"
                        t["logs"].append("\nTask cancelled by user.\n")
                        self.send_json({"success": True})
                    except Exception as e:
                        self.send_json({"error": f"Failed to cancel process: {e}"}, 500)
                else:
                    self.send_json({"error": "Task is not active"}, 400)
            else:
                self.send_json({"error": "Task not found"}, 404)
            return
            
        self.send_json({"error": "Endpoint not found"}, 404)

def run_server(port=8080):
    server_address = ("", port)
    httpd = HTTPServer(server_address, LuminateHTTPHandler)
    print(f"Luminate Installer Server running on http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server. Cleaning up active subprocesses...")
        for task_id, t in tasks.items():
            if t["status"] in ("converting", "installing") and t["proc"]:
                try:
                    t["proc"].terminate()
                except Exception:
                    pass
        httpd.server_close()

if __name__ == "__main__":
    port = 8080
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port)
