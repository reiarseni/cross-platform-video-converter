# 🎥 Cross-platform Video Converter

A **graphical** and **multiplatform** video converter built with **PyQt5** and **FFmpeg**, designed to **ensure compatibility with TVs and set-top boxes** when playing videos from a USB drive.

Many older TVs and set-top boxes fail to recognize certain formats like **MKV**, leading to the dreaded **"Format Not Supported"** error.  
This tool ensures that your videos are **converted into universally supported formats**, preventing playback issues.
Supports **Windows, macOS, and Linux**, offering batch conversion with adjustable quality settings.

## 🚀 Features
- ✅ **User-friendly GUI** with drag & drop support.
- ✅ **Batch conversion** for multiple video files.
- ✅ **Optimized formats for TV playback** (no more "Format Not Supported" errors).
- ✅ **Auto-detection of supported video formats** using FFmpeg.
- ✅ **Adjustable quality settings** (Low, Medium, High).
- ✅ **Progress tracking** with real-time updates.
- ✅ **Multi-platform support** (Windows, macOS, Linux).

## 🎯 Supported Output Formats  
To ensure the widest compatibility with **TVs, USB playback, and set-top boxes**, videos are converted to:  

| Format  | Codec  | Container |
|---------|--------|-----------|
| **MP4** | H.264  | `.mp4`    |
| **MP4** | H.265  | `.mp4`    |
| **AVI** | MPEG-4 | `.avi`    |
| **MKV** | H.264  | `.mkv`    |

> **Default format:** `MP4 (H.264 + AAC)` for maximum support across all TVs.  
> **Why?** Because some devices do not support **MKV**, **MOV**, or modern codecs like **VP9**.  

## 🛠️ Requirements
Before using this software, ensure you have the following installed:

- **Python 3.7+**
- **FFmpeg** (must be accessible in your system's PATH)

### 🔧 Installing FFmpeg  
FFmpeg is required for video processing. Install it as follows:  

#### 🖥️ **Windows**  
1. Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html).
2. Extract the archive and move the `bin` folder to `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to your **system's PATH**:
   - Search for **"Edit the system environment variables"**.
   - Click **"Environment Variables"**.
   - Under **"System Variables"**, find `Path`, edit it, and add `C:\ffmpeg\bin`.

#### 🍏 **macOS**  
1. Install FFmpeg via Homebrew:
   ```bash
   brew install ffmpeg
   ```

#### 🐧 **Linux**  
- **Debian/Ubuntu-based**:
  ```bash
  sudo apt update && sudo apt install ffmpeg
  ```
- **Arch Linux**:
  ```bash
  sudo pacman -S ffmpeg
  ```
- **Fedora**:
  ```bash
  sudo dnf install ffmpeg
  ```

## 🔧 Installation & Usage
Clone the repository and install dependencies:

```bash
git clone https://github.com/reiarseni/cross-platform-video-converter.git
cd cross-platform-video-converter
pip install -r requirements.txt
```

Run the application:

```bash
python video-converter.py
```

## 📜 License
This project is licensed under the MIT License.
```
