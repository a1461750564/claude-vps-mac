#!/bin/bash
# Preserve the existing Mac SSH entry; run Claude with ordinary user privileges.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
    printf '%s\n' 'This dispatcher is called by the existing root management SSH entry.' >&2
    exit 1
fi
cd /home/claude
exec /usr/sbin/runuser -u claude -- /usr/bin/env \
    -u CLAUDE_CONFIG_DIR -u SUDO_USER -u SUDO_UID -u SUDO_GID \
    HOME=/home/claude USER=claude LOGNAME=claude \
    PATH=/home/claude/.local/bin:/usr/local/bin:/usr/bin:/bin \
    /home/claude/.local/bin/claude-mac "$@"
