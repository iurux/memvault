# Run memvault in the background on macOS

Starts the API and the UI at login and restarts them if they crash. Keep the repos outside `~/Downloads`, `~/Desktop` and `~/Documents`: macOS blocks background services from reading those folders.

```bash
MEMVAULT=$(which memvault)
BUN=$(which bun)
UI_DIR=$HOME/code/memvault-ui
AGENTS=$HOME/Library/LaunchAgents

cat > $AGENTS/memvault.api.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>memvault.api</string>
  <key>ProgramArguments</key><array><string>$MEMVAULT</string><string>ui</string></array>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/memvault.log</string>
  <key>StandardErrorPath</key><string>/tmp/memvault.log</string>
</dict></plist>
EOF

cat > $AGENTS/memvault.ui.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>memvault.ui</string>
  <key>WorkingDirectory</key><string>$UI_DIR</string>
  <key>ProgramArguments</key><array>
    <string>$BUN</string><string>run</string><string>dev</string><string>--</string>
    <string>--port</string><string>4173</string><string>--strictPort</string>
  </array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$(dirname $BUN):/opt/homebrew/bin:/usr/bin:/bin</string></dict>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/memvault-ui.log</string>
  <key>StandardErrorPath</key><string>/tmp/memvault-ui.log</string>
</dict></plist>
EOF

launchctl load $AGENTS/memvault.api.plist $AGENTS/memvault.ui.plist
```

Then open http://localhost:4173.

| | |
|---|---|
| check status | `launchctl list \| grep memvault` |
| logs | `tail -f /tmp/memvault.log /tmp/memvault-ui.log` |
| restart API after updating | `launchctl kickstart -k gui/$(id -u)/memvault.api` |
| stop | `launchctl unload ~/Library/LaunchAgents/memvault.*.plist` |
