"""
setup.py — Cython extension build configuration

Build accelerated modules:
- _path_integral: Fast RK4 integration
- _operators: Fast 18-operator calculations

Usage:
    python setup.py build_ext --inplace
    
Requirements:
    pip install cython numpy
    
Windows Users:
    Install Visual Studio Build Tools:
    https://visualstudio.microsoft.com/visual-cpp-build-tools/
    Or use: pip install apexquantumict-accelerated (when published)
"""

from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy
import sys
import os

# Compiler flags - platform specific
extra_compile_args = []
extra_link_args = []

if sys.platform == 'win32':
    # Windows MSVC flags
    extra_compile_args = ['/O2', '/W3']
    
    # Fix Windows SDK path detection
    # Check multiple possible VS installation paths
    vs_paths = [
        r'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools',
        r'C:\Program Files\Microsoft Visual Studio\2022\BuildTools',
        r'C:\Program Files (x86)\Microsoft Visual Studio\18',  # Internal version
        r'C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools',
    ]
    
    for vs_path in vs_paths:
        if os.path.exists(vs_path):
            os.environ['DISTUTILS_USE_SDK'] = '1'
            os.environ['MSSdk'] = '1'
            print(f"Found VS at: {vs_path}")
            break
else:
    # Linux/Mac GCC/Clang flags
    extra_compile_args = ['-O3', '-ffast-math']
    if sys.platform != 'darwin':  # Not macOS
        extra_compile_args.append('-march=native')

extensions = [
    Extension(
        "trading.accelerated._path_integral",
        ["trading/accelerated/_path_integral.pyx"],
        include_dirs=[numpy.get_include()],
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args,
    ),
    Extension(
        "trading.accelerated._operators",
        ["trading/accelerated/_operators.pyx"],
        include_dirs=[numpy.get_include()],
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args,
    ),
]

setup(
    name="apexquantumict-accelerated",
    version="1.0.0",
    ext_modules=cythonize(
        extensions,
        annotate=True,
        compiler_directives={
            'language_level': '3',
            'boundscheck': False,
            'wraparound': False,
            'cdivision': True,
        }
    ),
    zip_safe=False,
)
