import sys
import socket
import threading
from pathlib import Path
import os

# Set environment variables to prevent WebKitGTK crashes on Wayland
os.environ["WEBKIT_DISABLE_DMABUF_RENDERER"] = "1"

# Set GTK application name for Wayland/GNOME window manager grouping
try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import GLib
    GLib.set_prgname('luminate-installer')
    GLib.set_application_name('Luminate Installer')
except Exception:
    pass

import webview
from app import run_server, tasks

def get_free_port():
    """Dynamically acquire a free local port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port

def main():
    port = get_free_port()
    
    # Run the HTTP backend server in a background thread
    server_thread = threading.Thread(target=run_server, args=(port,))
    server_thread.daemon = True
    server_thread.start()
    
    # Launch pywebview desktop interface
    window = webview.create_window(
        title="Luminate Installer",
        url=f"http://localhost:{port}",
        width=850,
        height=700,
        min_size=(650, 550)
    )
    
    def on_closed():
        # Terminate any running conversion/installation processes on exit
        for task_id, t in tasks.items():
            if t["status"] in ("converting", "installing") and t["proc"]:
                try:
                    t["proc"].terminate()
                except Exception:
                    pass
        sys.exit(0)
        
    window.events.closed += on_closed
    
    # Locate icon path (local dev fallback to global packaging destination)
    local_icon = Path(__file__).parent.resolve() / "luminate-installer.svg"
    global_icon = Path("/usr/share/pixmaps/luminate-installer.svg")
    icon_path = str(local_icon) if local_icon.exists() else (str(global_icon) if global_icon.exists() else None)
    
    webview.start(icon=icon_path)

if __name__ == "__main__":
    main()
