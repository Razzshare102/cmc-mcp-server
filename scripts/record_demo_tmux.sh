#!/usr/bin/env bash
# Run the CMC demo inside tmux and capture the real terminal screen
# every 0.5s. The Xvfb/xterm capture froze (the Inspector CLI disturbs
# the X terminal); tmux capture-pane gives the true screen state.
set -u
rm -rf /tmp/demo_cap /tmp/demo_frames
mkdir -p /tmp/demo_cap /tmp/demo_frames
rm -f /tmp/cmc-demo-*.txt ~/workspace/cmc-demo.mp4

tmux kill-session -t cmcdemo 2>/dev/null
tmux new-session -d -s cmcdemo -x 150 -y 40 \
  "bash /home/hatch/workspace/cmc-mcp-server/scripts/demo_record.sh; sleep 2"

i=0
while tmux has-session -t cmcdemo 2>/dev/null; do
  tmux capture-pane -t cmcdemo -p > "/tmp/demo_cap/frame_$(printf %04d $i).txt" 2>/dev/null
  tmux display-message -t cmcdemo -p '#{cursor_x} #{cursor_y}' > "/tmp/demo_cap/cursor_$(printf %04d $i).txt" 2>/dev/null
  i=$((i + 1))
  sleep 0.5
done
echo "captured $i frames"
ls /tmp/demo_cap/frame_*.txt | wc -l
