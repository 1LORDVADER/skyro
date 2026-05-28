from setuptools import setup, find_packages

setup(
    name="vault33-digital",
    version="1.6",
    description="VAULT 33 – Revolutionary Autonomous Data Storage System",
    author="LORD VADER (@SithTrades1)",
    packages=find_packages(),
    python_requires=">=3.12",
    install_requires=[
        # FIX GAP-02: Previously empty — SDK silently fell back to insecure XOR cipher.
        # cryptography is required for AES-256-GCM encryption (vault33_production.py).
        # flask + flask-cors are required for the REST API server (vault33_api.py).
        "cryptography>=41.0",
        "flask>=3.0",
        "flask-cors>=4.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "vault33=cli:main",
            "vault33-api=vault33_api:app",
        ],
    },
)
