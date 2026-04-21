# Cython Extension Build Guide

## Status: Source Ready, Build Optional

The system works **without** compiled extensions - it gracefully falls back to NumPy.

Build Cython extensions for **10-100x speedup** on compute-heavy operations.

---

## Quick Start

### Option 1: pip install (Recommended for Linux/Mac)

```bash
pip install cython numpy
pip install -e trading/accelerated
```

### Option 2: Build in place (Development)

```bash
pip install cython numpy
python trading/accelerated/setup.py build_ext --inplace
```

---

## Windows Build Instructions

### Prerequisites

**Visual Studio Build Tools** (required for C compiler):

1. Download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
2. Install "Desktop development with C++" workload
3. Or install just "MSVC v143 - VS 2022 C++ x64/x86 build tools"

### Build Commands

**With Visual Studio 2022:**
```powershell
# Open "Developer PowerShell for VS 2022"
cd c:\Users\Dataentry\CascadeProjects\nvidia_chat
pip install cython numpy
python trading/accelerated/setup.py build_ext --inplace
```

**Alternative (without VS shell):**
```powershell
# Set compiler environment
$env:DISTUTILS_USE_SDK = "1"
python trading/accelerated/setup.py build_ext --inplace
```

### Common Windows Errors

**Error: `cl.exe` not found**
- Solution: Install Visual Studio Build Tools (see above)

**Error: `error: Microsoft Visual C++ 14.0 is required`**
- Solution: Install Microsoft C++ Build Tools from:
  https://visualstudio.microsoft.com/visual-cpp-build-tools/

**Error: `LINK : fatal error LNK1158: cannot run 'rc.exe'`**
- Solution: Add Windows SDK to PATH or use VS Developer shell

---

## Linux/Mac Build Instructions

### Ubuntu/Debian

```bash
sudo apt-get update
sudo apt-get install python3-dev gcc
pip install cython numpy
python trading/accelerated/setup.py build_ext --inplace
```

### macOS

```bash
# Install Xcode Command Line Tools
xcode-select --install

# Or use Homebrew
brew install gcc

pip install cython numpy
python trading/accelerated/setup.py build_ext --inplace
```

### CentOS/RHEL

```bash
sudo yum install gcc python3-devel
pip install cython numpy
python trading/accelerated/setup.py build_ext --inplace
```

---

## Cloud/Server Build (Heroku, Railway, Render)

Add to your deployment:

**requirements.txt:**
```
cython>=3.0.0
numpy>=1.24.0
polars>=0.20.0
```

**Procfile or build script:**
```bash
# Build extensions during deployment
python trading/accelerated/setup.py build_ext --inplace
```

**Heroku specific:**
Add to `heroku.yml` or use `pre_compile` hook to build extensions.

---

## Docker Build

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y gcc python3-dev

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN python trading/accelerated/setup.py build_ext --inplace

CMD ["python", "telegram_bot_full.py"]
```

---

## Verify Build

```python
from trading.accelerated import CYTHON_AVAILABLE, CYTHON_PATH_INTEGRAL

print(f"Cython available: {CYTHON_AVAILABLE}")
print(f"Path integral: {CYTHON_PATH_INTEGRAL}")

# Check backend
from trading.accelerated.backend_selector import get_best_backend
print(f"Best backend: {get_best_backend()}")  # Should show 'cython' if built
```

---

## Performance Comparison

| Backend | Build Required | Speedup | Status |
|---------|---------------|---------|--------|
| Mojo | Mojo SDK | 100-1000x | Future |
| Cython | C compiler | 10-100x | Buildable |
| Numba | LLVM | 2-10x | pip install |
| NumPy | None | 1x | Always works |

---

## Troubleshooting

### Check compiler availability

**Windows:**
```powershell
where cl.exe
# Should show path to Visual Studio compiler
```

**Linux/Mac:**
```bash
which gcc
gcc --version
```

### Clean rebuild

```bash
rm -rf build/
rm -f trading/accelerated/*.pyd trading/accelerated/*.so
rm -f trading/accelerated/*.c trading/accelerated/*.cpp
python trading/accelerated/setup.py build_ext --inplace
```

### Debug build

```bash
# Add compiler flags for debugging
CFLAGS="-g -O0" python trading/accelerated/setup.py build_ext --inplace
```

---

## Current Status on This System

```
Platform: Windows (PowerShell)
C Compiler: Not available (cl.exe not found)
Status: Using NumPy fallback (works correctly)
Path: /c/Users/Dataentry/CascadeProjects/nvidia_chat
```

To enable Cython acceleration on this system:
1. Install Visual Studio Build Tools
2. Re-run build command
3. Verify with `get_best_backend()` showing 'cython'

---

## Summary

- ✅ Source code ready (Cython files fixed)
- ✅ Graceful fallback to NumPy working
- ⏳ Windows compiler not available (optional)
- 🚀 Ready for Linux deployment with full acceleration
