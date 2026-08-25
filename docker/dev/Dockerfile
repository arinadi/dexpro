FROM termux/termux-docker

# ═══════════════════════════════════════════════
#  dexpro Dev — Termux packages for the native
#  session (Phase 1) + TUI logic testing
# ═══════════════════════════════════════════════

# Termux has no FHS /bin — everything lives under $PREFIX. Without this,
# RUN falls back to /bin/sh, which this image doesn't have (confirmed:
# XLabs' identical Dockerfile hits the same buildah/crun failure).
SHELL ["/data/data/com.termux/files/usr/bin/bash", "-c"]

# /data/data/ is 771 root:root — UID 1000 can't traverse it.
RUN mkdir -p /data/data/com.termux/files/home \
    && chmod 755 /data/data /data/data/com.termux \
      /data/data/com.termux/files /data/data/com.termux/files/home

USER 1000:1000
# x11-repo has to be installed and its package list picked up (a second
# `pkg update`) before xfce4/xfce4-terminal are visible to apt at all —
# they live in that repo, not termux-main.
RUN pkg update -y && pkg install -y x11-repo \
    && pkg update -y && pkg install -y \
        python3 \
        curl \
        git \
        rsync \
        dbus \
        xfce4 \
        xfce4-terminal \
        pulseaudio \
    && pkg clean

USER root:root

WORKDIR /data/data/com.termux/files/home

CMD ["/data/data/com.termux/files/usr/bin/bash"]
