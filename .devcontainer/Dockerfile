FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/home/vscode/.cargo \
    PATH=/home/vscode/.cargo/bin:/usr/local/cargo/bin:${PATH}

RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends build-essential unzip \
    && rm -rf /var/lib/apt/lists/* \
    && curl --proto '=https' --tlsv1.2 -fsSL https://sh.rustup.rs \
        | CARGO_HOME=/usr/local/cargo sh -s -- -y --profile minimal --default-toolchain stable \
    && CARGO_HOME=/usr/local/cargo rustup toolchain install nightly --profile minimal \
        --component clippy --component miri --component rust-analyzer \
        --component rust-docs --component rust-src --component rustfmt \
        --target wasm32-unknown-unknown \
    && chmod -R a+rX "${RUSTUP_HOME}" /usr/local/cargo \
    && install -d -o vscode -g vscode "${CARGO_HOME}"
