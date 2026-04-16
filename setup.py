from setuptools import setup, find_packages

setup(
    name="coding-agent-guard",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "ollama>=0.3.0",
        "pyyaml>=6.0",
        "python-dotenv>=1.0.0",
        "streamlit>=1.37.0",
        "pandas>=2.0.0",
        "plotly>=5.18.0",
    ],
    entry_points={
        "console_scripts": [
            "coding-agent-guard=coding_agent_guard.core.guard:main",
        ],
    },
    author="Coding Agent Guard Contributors",
    description="A standalone security primitive for AI coding agents",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/packetcraft/Coding-Agent-Guard",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
)
