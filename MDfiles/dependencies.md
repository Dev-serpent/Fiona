# Fiona External Dependencies

This document lists all external tools, libraries, and system commands required to run Fiona's various modules.

## 🐍 Python Libraries

These can generally be installed via `pip`.

| Library | Module(s) | Purpose |
| :--- | :--- | :--- |
| `pynput` | QuikTieper, TerminalAssist | Global keyboard/mouse listener and tracking. |
| `numpy` | DataClient, EyeControl, Vsee | Numerical processing for research and vision data. |
| `pandas` | DataClient | CSV and data table manipulation. |
| `requests` | EyeControl, CamComs | HTTP communication with IP cameras and peer nodes. |
| `opencv-python` (cv2) | EyeControl | Camera feed processing. |
| `mediapipe` | EyeControl | Machine learning models for eye/face tracking. |
| `pyautogui` | EyeControl | Programmatic mouse control from vision data. |
| `tkinter` | PhiConnect, DataClient, Vsee | GUI framework for standalone applications. |
| `faster-whisper` | FionaCore (Voice) | High-performance speech-to-text engine. |
| `sounddevice` | FionaCore (Voice) | Microphone access and audio recording. |

## 🛠️ System Tools (CLI Commands)

These should be available in your system's `PATH`.

### Core System Monitoring (TerminalAssist)
*   **`btop`**: Required for the "System Monitor" quick action.
*   **`ip`**: Used to retrieve network interface and IP metadata.
*   **`ps`**: Used to identify top CPU-consuming processes.
*   **`systemctl`**: Used to monitor failed units and manage the host service.
*   **`zellij`**: Required for the terminal multiplexer dashboard layouts.

### Spatial Awareness & Control
*   **`kdotool`**: **Highly Recommended** for KDE Wayland/X11. Used for accurate mouse tracking and window management.
*   **`xdotool`**: Used for mouse tracking and window metadata on X11 sessions.
*   **`xprop`**: Fallback for window metadata retrieval on X11.

### Session & Security
*   **`loginctl`**: Session locking and management (KDE).
*   **`qdbus-qt5`**: KDE session logout control.
*   **`gnome-screensaver-command`**: GNOME session locking.
*   **`gnome-session-quit`**: GNOME session logout.
*   **`ufw`**: Firewall status reporting in the dashboard.
*   **`checkupdates`**: (Arch Linux) Pending update counts for the dashboard.
*   **`sudo` / `pkexec`**: Privileged execution for systemd management and certain spatial tools.

### Hardware & Feedback
*   **`nvidia-smi`**: Required for GPU utilization and temperature reporting.
*   **`notify-send`**: Desktop notifications for action results.
*   **`spd-say`**: Text-to-speech feedback for voice commands.

## 🖥️ Desktop Environments

Fiona features specialized logic for the following environments:
*   **KDE Plasma**: Full support for Wayland tracking via `kdotool`.
*   **GNOME**: Native session control support.
*   **XFCE / Generic X11**: Supported via `xdotool` and `xprop`.

## 🤖 Optional Services
*   **LM Studio**: Required for the `Agent` module (`fiona agent status`, `fiona agent ask`). Must be running locally on port `1234` by default.
