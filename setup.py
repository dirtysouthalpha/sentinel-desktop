from setuptools import setup, find_packages

setup(
    name="sentinel-desktop",
    version="28.0.0",
    description="AI-powered Windows desktop automation assistant",
    author="Sentinel Prime",
    author_email="dev@dirtysouthalpha.com",
    url="https://github.com/dirtysouthalpha/sentinel-desktop",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "customtkinter>=5.0.0",
        "pyautogui>=0.9.54",
        "psutil>=5.9.0",
        "requests>=2.28.0",
        "Pillow>=9.0.0",
    ],
    entry_points={
        "console_scripts": [
            "sentinel-cli=src.cli:cli_main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3",
    ],
)
