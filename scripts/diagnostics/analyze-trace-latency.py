import argparse
import json
import os
from typing import List, Dict, Optional


def read_jsonl(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return []
    items = []
    with open(path, "r") as f:
        for line in f:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def _stats(data: List[float]) -> str:
    if not data:
        return "N/A"
    return (
        f"Avg={sum(data) / len(data):.1f}ms, Min={min(data)}ms, "
        f"Max={max(data)}ms, p50={_percentile(data, 50):.1f}ms, "
        f"p99={_percentile(data, 99):.1f}ms, Count={len(data)}"
    )


def _percentile(data: List[float], pct: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * pct / 100.0)
    idx = min(idx, len(sorted_data) - 1)
    return sorted_data[idx]


def analyze_latency(session_dir: str):
    net_path = os.path.join(session_dir, "logs", "input_events_network.jsonl")
    x11_path = os.path.join(session_dir, "logs", "input_events.jsonl")
    win_path = os.path.join(session_dir, "logs", "input_events_windows.jsonl")

    net_events = read_jsonl(net_path)
    x11_events = [e for e in read_jsonl(x11_path) if e.get("event") == "button_press"]
    win_events = [e for e in read_jsonl(win_path) if e.get("event") == "mousedown"]

    print(f"Analyzing session (mouse): {os.path.basename(session_dir)}")
    print(
        f"Events: Network={len(net_events)}, X11={len(x11_events)}, Windows={len(win_events)}"
    )
    print("-" * 40)

    latencies_net_x11: List[float] = []
    latencies_x11_win: List[float] = []
    latencies_total: List[float] = []

    x11_cursor = 0
    win_cursor = 0

    for net in net_events:
        if net.get("event") != "vnc_pointer":
            continue

        vnc_mask = net.get("button_mask", 0)
        if vnc_mask == 0:  # Filter motion
            continue

        net_ts = net["timestamp_epoch_ms"]
        match_x11: Optional[Dict] = None

        # 1. Match Network -> X11
        for i in range(x11_cursor, len(x11_events)):
            x11 = x11_events[i]
            x11_ts = x11["timestamp_epoch_ms"]

            # X11 event should be after Network event within a reasonable window
            delta = x11_ts - net_ts
            if 0 <= delta <= 500:
                # Basic button check (Net mask 1 = left, X11 btn 1 = left)
                x11_btn = x11.get("button", 0)
                matched_btn = False
                if (vnc_mask & 1) and x11_btn == 1:
                    matched_btn = True
                elif (vnc_mask & 2) and x11_btn == 2:
                    matched_btn = True
                elif (vnc_mask & 4) and x11_btn == 3:
                    matched_btn = True

                if matched_btn:
                    match_x11 = x11
                    x11_cursor = i + 1
                    break

        if match_x11:
            delta_nx = match_x11["timestamp_epoch_ms"] - net_ts
            latencies_net_x11.append(delta_nx)

            # 2. Match X11 -> Windows
            match_win = None
            x11_ts = match_x11["timestamp_epoch_ms"]
            for j in range(win_cursor, len(win_events)):
                win = win_events[j]
                win_ts = win["timestamp_epoch_ms"]
                delta_xw = win_ts - x11_ts

                if 0 <= delta_xw <= 500:
                    win_btn = win.get("button", "").lower()
                    x11_b = match_x11.get("button", 0)
                    matched_w = False
                    if x11_b == 1 and "left" in win_btn:
                        matched_w = True
                    elif x11_b == 2 and "middle" in win_btn:
                        matched_w = True
                    elif x11_b == 3 and "right" in win_btn:
                        matched_w = True

                    if matched_w:
                        match_win = win
                        win_cursor = j + 1
                        break

            if match_win:
                delta_xw = (
                    match_win["timestamp_epoch_ms"] - match_x11["timestamp_epoch_ms"]
                )
                latencies_x11_win.append(delta_xw)
                latencies_total.append(match_win["timestamp_epoch_ms"] - net_ts)
                print(
                    f"MATCH: Net({net_ts}) -> X11(+{delta_nx}ms) -> "
                    f"Win(+{delta_xw}ms) Total={match_win['timestamp_epoch_ms'] - net_ts}ms"
                )
            else:
                print(f"PARTIAL: Net({net_ts}) -> X11(+{delta_nx}ms) -> Win(MISSING)")
        else:
            print(f"MISSING: Net({net_ts}) -> X11(MISSING)")

    print("-" * 40)
    print(f"Network -> X11 Latency: {_stats(latencies_net_x11)}")
    print(f"X11 -> Windows Latency: {_stats(latencies_x11_win)}")
    print(f"Total End-to-End Latency: {_stats(latencies_total)}")


def analyze_keyboard_latency(session_dir: str):
    """Analyze API /input/key -> Windows trace latency for keyboard injection.

    Correlates API input events (agent_key with trace_id) against Windows-side
    trace events (key_down/key_up) to measure end-to-end keyboard latency.
    """
    api_log = os.path.join(session_dir, "logs", "input_events.jsonl")
    win_log = os.path.join(session_dir, "logs", "input_events_windows.jsonl")

    # Index API key events by trace_id
    api_requests: Dict[str, Dict] = {}
    api_completes: Dict[str, Dict] = {}
    for event in read_jsonl(api_log):
        if event.get("event") != "agent_key":
            continue
        trace_id = event.get("trace_id")
        if not trace_id:
            continue
        if event.get("phase") == "request":
            api_requests[trace_id] = event
        elif event.get("phase") == "complete":
            api_completes[trace_id] = event

    # Index Windows-side key events by trace_id
    win_key_downs: Dict[str, Dict] = {}
    win_key_ups: Dict[str, Dict] = {}
    for event in read_jsonl(win_log):
        trace_id = event.get("trace_id")
        if not trace_id:
            continue
        if event.get("event") == "key_down":
            win_key_downs[trace_id] = event
        elif event.get("event") == "key_up":
            win_key_ups[trace_id] = event

    print(f"Analyzing keyboard latency for session: {os.path.basename(session_dir)}")
    print(
        f"Events: API requests={len(api_requests)}, "
        f"API completes={len(api_completes)}, "
        f"Windows key_down={len(win_key_downs)}, "
        f"Windows key_up={len(win_key_ups)}"
    )
    print("-" * 50)

    api_to_win_latencies: List[float] = []
    matched = 0
    unmatched_api = 0

    for trace_id, req in api_requests.items():
        req_ts = req.get("timestamp_epoch_ms", 0)
        if not req_ts:
            unmatched_api += 1
            continue

        win_down = win_key_downs.get(trace_id)
        keys = req.get("keys", "?")[:40]
        backend = req.get("via", "?")

        if win_down:
            win_ts = win_down.get("timestamp_epoch_ms", 0)
            if win_ts:
                delta = win_ts - req_ts
                api_to_win_latencies.append(delta)
                up = "up" if win_key_ups.get(trace_id) else "no-up"
                print(
                    f"MATCH: [{backend}] \"{keys}\" "
                    f"API({req_ts}) -> Win(+{delta}ms) {up}"
                )
                matched += 1
                continue

        # Fallback: match by time proximity within 5s window
        matched_prox = False
        for wid, wd in win_key_downs.items():
            w_ts = wd.get("timestamp_epoch_ms", 0)
            if w_ts and abs(w_ts - req_ts) < 5000:
                delta = w_ts - req_ts
                api_to_win_latencies.append(delta)
                print(
                    f"PROXIMITY: [{backend}] \"{keys}\" "
                    f"API({req_ts}) -> Win(+{delta}ms)"
                )
                matched_prox = True
                matched += 1
                break
        if not matched_prox:
            print(f"UNMATCHED: [{backend}] \"{keys}\" API({req_ts}) -> Win(MISSING)")
            unmatched_api += 1

    print("-" * 50)
    print(f"API -> Windows Latency: {_stats(api_to_win_latencies)}")
    print(f"Matched: {matched}, Unmatched API: {unmatched_api}")

    # Per-backend breakdown
    ahk_lats: List[float] = []
    xdo_lats: List[float] = []
    for trace_id, req in api_requests.items():
        backend = req.get("via", "")
        win_down = win_key_downs.get(trace_id)
        if win_down:
            req_ts = req.get("timestamp_epoch_ms", 0)
            win_ts = win_down.get("timestamp_epoch_ms", 0)
            if req_ts and win_ts:
                delta = win_ts - req_ts
                if backend == "ahk":
                    ahk_lats.append(delta)
                elif backend == "xdotool":
                    xdo_lats.append(delta)

    if ahk_lats:
        print(f"\nAHK backend: {_stats(ahk_lats)}")
    if xdo_lats:
        print(f"xdotool backend: {_stats(xdo_lats)}")
    if not ahk_lats and not xdo_lats:
        print("\nNo backend-specific latencies available (no matched events).")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze input latency from trace logs."
    )
    parser.add_argument(
        "--session-dir",
        help="Session directory to analyze. Defaults to current session.",
        default="",
    )
    parser.add_argument(
        "--mode",
        help="Analysis mode: mouse (default, VNC->X11->Win) or keyboard (API->Win).",
        default="mouse",
        choices=["mouse", "keyboard"],
    )
    args = parser.parse_args()

    session_dir = args.session_dir
    if not session_dir:
        path = "/tmp/winebot_current_session"
        if os.path.exists(path):
            with open(path, "r") as f:
                session_dir = f.read().strip()

    if not session_dir or not os.path.exists(session_dir):
        print("Error: Session directory not found.")
        return 1

    if args.mode == "keyboard":
        analyze_keyboard_latency(session_dir)
    else:
        analyze_latency(session_dir)
    return 0


if __name__ == "__main__":
    main()
