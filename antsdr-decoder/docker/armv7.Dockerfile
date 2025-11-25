FROM ghcr.io/cross-rs/armv7-unknown-linux-gnueabihf:edge

RUN dpkg --add-architecture armhf && \
    apt-get update -qq && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends \
        pkg-config                  \
        libpcap-dev:armhf           \ 
        libpcap0.8:armhf            \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
