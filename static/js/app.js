document.addEventListener("DOMContentLoaded", () => {
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    const sysArch = document.getElementById("sys-arch");
    const sysDebtap = document.getElementById("sys-debtap");
    
    const taskCard = document.getElementById("task-card");
    const taskBadge = document.getElementById("task-badge");
    const taskFilename = document.getElementById("task-filename");
    const progressBar = document.getElementById("progress-bar");
    const progressPercent = document.getElementById("progress-percent");
    const terminalLogs = document.getElementById("terminal-logs");
    const btnCancel = document.getElementById("btn-cancel");
    
    // Stages
    const stageUpload = document.getElementById("stage-upload");
    const stageConvert = document.getElementById("stage-convert");
    const stageInstall = document.getElementById("stage-install");
    const stageComplete = document.getElementById("stage-complete");
    
    let activeTaskId = null;
    let pollInterval = null;
    let uploadController = null;

    // Check system status initially
    checkSystemStatus();

    // Prevent default drag/drop behaviors on window to avoid browser navigation
    ["dragenter", "dragover", "dragleave", "drop"].forEach(eventName => {
        window.addEventListener(eventName, (e) => {
            e.preventDefault();
        }, false);
    });

    function checkSystemStatus() {
        fetch("/api/status")
            .then(res => res.json())
            .then(data => {
                // Update Arch Status
                if (data.arch) {
                    sysArch.className = "status-item ok";
                    sysArch.querySelector(".text").textContent = "Arch Linux Detected";
                } else {
                    sysArch.className = "status-item error";
                    sysArch.querySelector(".text").textContent = "Non-Arch System";
                }
                
                // Update Debtap Status
                if (data.debtap) {
                    sysDebtap.className = "status-item ok";
                    sysDebtap.querySelector(".text").textContent = "Debtap Ready";
                } else {
                    sysDebtap.className = "status-item error";
                    sysDebtap.querySelector(".text").textContent = "Debtap Missing";
                }
            })
            .catch(err => {
                sysArch.className = "status-item error";
                sysArch.querySelector(".text").textContent = "Offline";
                sysDebtap.className = "status-item error";
                sysDebtap.querySelector(".text").textContent = "Offline";
            });
    }

    // Drag and Drop Event Listeners
    ["dragenter", "dragover"].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            if (activeTaskId) return;
            dropZone.classList.add("dragover");
        }, false);
    });

    ["dragleave", "drop"].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.classList.remove("dragover");
        }, false);
    });

    dropZone.addEventListener("drop", (e) => {
        if (activeTaskId) return;
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    }, false);

    // Manual file browser browse button
    dropZone.addEventListener("click", () => {
        if (activeTaskId) return;
        fileInput.click();
    });

    fileInput.addEventListener("change", () => {
        if (fileInput.files.length > 0) {
            handleFileUpload(fileInput.files[0]);
        }
    });

    function handleFileUpload(file) {
        if (activeTaskId) return;
        
        // Check file extension
        const filename = file.name;
        const ext = filename.split(".").pop().toLowerCase();
        
        if (!["deb", "appimage", "zst", "xz"].includes(ext)) {
            alert("Unsupported file format! Please drag a .deb, .AppImage, or .pkg.tar.zst package.");
            return;
        }

        // Show Task Card & Reset UI
        taskCard.classList.remove("hidden");
        taskFilename.textContent = filename;
        taskBadge.textContent = "Uploading";
        taskBadge.className = "badge";
        progressBar.style.width = "0%";
        progressPercent.textContent = "0%";
        terminalLogs.textContent = "Initializing upload...\n";
        
        // Reset pipeline stages
        [stageUpload, stageConvert, stageInstall, stageComplete].forEach(stg => {
            stg.className = "stage";
        });
        
        stageUpload.classList.add("active");

        // Prepare multipart data
        const formData = new FormData();
        formData.append("file", file);

        // Disable Dropzone
        dropZone.style.opacity = "0.5";
        dropZone.style.pointerEvents = "none";

        uploadController = new AbortController();

        fetch("/api/upload", {
            method: "POST",
            body: formData,
            signal: uploadController.signal
        })
        .then(res => {
            if (!res.ok) throw new Error("Upload failed");
            return res.json();
        })
        .then(data => {
            if (data.success) {
                activeTaskId = data.task_id;
                stageUpload.className = "stage done";
                stageConvert.className = "stage active";
                taskBadge.textContent = "Processing";
                
                // Start Polling Task Status
                startPollingTask(data.task_id, ext);
            } else {
                throw new Error(data.error || "Upload rejected");
            }
        })
        .catch(err => {
            resetDropZone();
            taskBadge.textContent = "Failed";
            taskBadge.classList.add("failed");
            stageUpload.className = "stage error";
            terminalLogs.textContent += `\nError: ${err.message}\n`;
        });
    }

    function startPollingTask(taskId, fileExt) {
        if (pollInterval) clearInterval(pollInterval);
        
        pollInterval = setInterval(() => {
            fetch(`/api/task/${taskId}`)
                .then(res => res.json())
                .then(data => {
                    if (data.error) {
                        clearInterval(pollInterval);
                        return;
                    }
                    
                    // Update Logs
                    terminalLogs.textContent = data.logs;
                    terminalLogs.scrollTop = terminalLogs.scrollHeight; // Auto-scroll
                    
                    // Update Context
                    const taskContext = document.getElementById("task-context");
                    if (taskContext && data.context) {
                        taskContext.textContent = data.context;
                    }
                    
                    // Update Progress
                    progressBar.style.width = `${data.progress}%`;
                    progressPercent.textContent = `${data.progress}%`;
                    
                    // Update Badges & Stages based on status
                    taskBadge.className = "badge";
                    
                    if (data.status === "converting") {
                        taskBadge.textContent = "Converting";
                        taskBadge.classList.add("converting");
                        stageUpload.className = "stage done";
                        stageConvert.className = "stage active";
                    } 
                    else if (data.status === "installing") {
                        taskBadge.textContent = "Installing";
                        taskBadge.classList.add("installing");
                        stageUpload.className = "stage done";
                        stageConvert.className = fileExt === "deb" ? "stage done" : "stage";
                        stageInstall.className = "stage active";
                    } 
                    else if (data.status === "completed") {
                        taskBadge.textContent = "Completed";
                        taskBadge.classList.add("completed");
                        
                        stageUpload.className = "stage done";
                        stageConvert.className = fileExt === "deb" ? "stage done" : "stage";
                        stageInstall.className = "stage done";
                        stageComplete.className = "stage done";
                        
                        progressBar.style.width = "100%";
                        progressPercent.textContent = "100%";
                        
                        clearInterval(pollInterval);
                        resetDropZone();
                        checkSystemStatus();
                    } 
                    else if (data.status === "failed") {
                        taskBadge.textContent = "Failed";
                        taskBadge.classList.add("failed");
                        
                        // Mark active/installing stage as error
                        if (stageInstall.classList.contains("active")) {
                            stageInstall.className = "stage error";
                        } else if (stageConvert.classList.contains("active")) {
                            stageConvert.className = "stage error";
                        } else {
                            stageUpload.className = "stage error";
                        }
                        
                        clearInterval(pollInterval);
                        resetDropZone();
                    }
                })
                .catch(err => {
                    console.error("Polling error:", err);
                });
        }, 500);
    }

    // Cancel Button Click
    btnCancel.addEventListener("click", () => {
        if (uploadController && !activeTaskId) {
            if (confirm("Cancel file upload?")) {
                uploadController.abort();
                terminalLogs.textContent += "\nUpload aborted by user.";
                taskBadge.textContent = "Aborted";
                taskBadge.className = "badge failed";
                stageUpload.className = "stage error";
                resetDropZone();
            }
            return;
        }
        
        if (!activeTaskId) return;
        
        if (confirm("Are you sure you want to cancel the installation/conversion?")) {
            fetch(`/api/cancel/${activeTaskId}`, { method: "POST" })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        terminalLogs.textContent += "\nCancelling process...";
                    }
                })
                .catch(err => console.error("Cancel error:", err));
        }
    });
    
    function resetDropZone() {
        activeTaskId = null;
        uploadController = null;
        dropZone.style.opacity = "1";
        dropZone.style.pointerEvents = "auto";
        fileInput.value = ""; // Clear file input
    }
});
