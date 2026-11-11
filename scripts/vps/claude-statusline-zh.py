#!/usr/bin/python3
"""Chinese status line with per-request throughput from local transcript metadata."""

from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
import unicodedata

RESET = "\033[0m"
COLORS = {"teal": 37, "purple": 139, "green": 112, "blue": 33,
          "yellow": 220, "red": 203, "dim": 242}
ANSI = re.compile(r"\033\[[0-9;]*m")
COMPACT_WINDOW = "CLAUDE_CODE_AUTO_COMPACT_WINDOW"


def color(text, name):
    return f"\033[38;5;{COLORS[name]}m{text}{RESET}"


def bar(percent, size, name):
    filled = int(min(100, percent or 0) * size / 100)
    return color("[" + "█" * filled + "░" * (size - filled) + "]", name)


def countdown(reset, now):
    if reset is None:
        return "—"
    minutes = max(0, math.ceil((reset - now) / 60))
    days, minutes = divmod(minutes, 1440)
    hours, minutes = divmod(minutes, 60)
    return (f"{days}天" if days else "") + (f"{hours}时" if hours else "") + f"{minutes}分"


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isfinite(value) and value >= 0:
            return value
    return None


def compact_window():
    """Prefer the CLI's effective environment, then the adjacent user settings."""
    value = os.environ.get(COMPACT_WINDOW)
    if value is None:
        try:
            settings = json.loads(Path(__file__).with_name("settings.json").read_text(encoding="utf-8"))
            value = (settings.get("env") or {}).get(COMPACT_WINDOW)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, AttributeError) as error:
            print(f"statusline-zh: cannot read compact window from settings: {error}", file=sys.stderr)
            return None
    if value is None:
        return None
    try:
        limit = float(value) if not isinstance(value, bool) else 0
    except (ValueError, TypeError, OverflowError):
        limit = 0
    if math.isfinite(limit) and limit > 0:
        return limit
    print(f"statusline-zh: ignoring invalid {COMPACT_WINDOW}", file=sys.stderr)
    return None


def terminal_width():
    try:
        columns = int(os.environ.get("COLUMNS", "120"))
    except ValueError:
        columns = 120
    return max(1, columns - 4)


def output_rate(transcript_path):
    """Read at most 512 KiB on log changes; cache only timing/token metadata."""
    if not transcript_path:
        return None
    transcript = Path(transcript_path)
    try:
        info = transcript.stat()
    except FileNotFoundError:  # A new session may not have a transcript yet.
        return None
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("transcript is not a regular file")
    fingerprint = [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]
    cache_dir = Path(__file__).parent / "cache" / "statusline-zh"
    cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = hashlib.sha256(str(transcript.resolve()).encode()).hexdigest()
    cache_file = cache_dir / (key + ".json")
    try:
        cached = json.loads(cache_file.read_text())
    except FileNotFoundError:
        cached = {}
    except ValueError as error:
        print(f"statusline-zh: rebuilding invalid speed cache: {error}", file=sys.stderr)
        cached = {}
    if not isinstance(cached, dict):
        print("statusline-zh: rebuilding speed cache with invalid structure", file=sys.stderr)
        cached = {}
    if cached.get("version") == 1 and cached.get("fingerprint") == fingerprint:
        measurement = cached.get("measurement")
        if measurement is None:
            return None
        if isinstance(measurement, dict) and number(measurement.get("tps")) is not None:
            return measurement
        print("statusline-zh: rebuilding speed cache with invalid measurement", file=sys.stderr)

    requests, latest = {}, None
    with transcript.open("rb") as stream:
        start = max(0, info.st_size - 512 * 1024)
        stream.seek(max(0, start - 1))
        partial = start > 0 and stream.read(1) != b"\n"
        stream.seek(start)
        chunk = stream.read(512 * 1024)
    if partial:
        chunk = chunk.partition(b"\n")[2]
    for line in chunk.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            continue  # An actively written final line is not complete yet.
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError("transcript record is not a JSON object")
        if record.get("type") == "api-request" and record.get("id"):
            requests[record.get("id")] = record
        elif record.get("type") == "assistant" and not record.get("isSidechain"):
            # Every content block repeats whole-response usage: use the last
            # block timestamp and its token count, never sum repeated blocks.
            latest = None if record.get("isApiErrorMessage") else record

    measurement = None
    if latest:
        reference = latest.get("requestRef")
        request = requests.get(reference) if reference else None
        count = number(((latest.get("message") or {}).get("usage") or {}).get("output_tokens"))
        if request and count is not None and count > 0:
            began = datetime.fromisoformat(request["timestamp"].replace("Z", "+00:00"))
            ended = datetime.fromisoformat(latest["timestamp"].replace("Z", "+00:00"))
            duration = (ended - began).total_seconds()
            if duration > 0:
                measurement = {"output_tokens": count, "duration_ms": duration * 1000,
                               "tps": count / duration, "completed_at": latest["timestamp"]}
    state = {"version": 1, "fingerprint": fingerprint, "measurement": measurement}
    fd, temporary = tempfile.mkstemp(prefix=".speed-", dir=cache_dir)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(state, stream, allow_nan=False)
        os.replace(temporary, cache_file)  # mkstemp creates a private 0600 file.
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return measurement


def clean(value):
    return " ".join("".join(c for c in str(value) if c.isprintable()).split())


def tokens(value):
    return f"{value / 1000:.0f}k" if value >= 1000 else str(int(value))


def width(text):
    return sum(0 if unicodedata.combining(c) else
               2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
               for c in ANSI.sub("", text))


def shorten(text, columns):
    if width(text) <= columns:
        return text
    result = ""
    for char in ANSI.sub("", text):
        if width(result + char) > columns - 1:
            break
        result += char
    return result + "…"


def emit(parts, columns):
    line = ""
    for part in parts:
        part = shorten(part, columns)
        combined = line + color(" | ", "dim") + part if line else part
        if width(combined) > columns:
            print(line)
            line = part
        else:
            line = combined
    if line:
        print(line)


def row_width(parts):
    return sum(map(width, parts)) + 3 * (len(parts) - 1)


def layout(model, context, cache, quotas, cost, columns, speed=None, speed_error=False):
    minimum_bar = 2
    if speed is None:
        speed_text = None
    elif 0 < speed < 0.1:
        speed_text = "<0.1"
    else:
        speed_text = f"≈{speed:.1f}" if speed < 1 else f"≈{speed:.0f}"

    def top_parts(size, compact):
        model_part = model.replace(" · ", "·") if compact else model
        cache_part = cache.replace("缓存 ", "缓存", 1) if compact else cache
        if speed_error:
            output = "输出 日志异常"
        elif speed_text is not None:
            output = f"输出{speed_text}{'' if compact else ' '}t/s"
        else:
            output = "输出 —" if compact else "输出 待统计"
        return [model_part, context(size, compact),
                color(output, "yellow" if speed_error else "green"), cache_part]

    for compact in (False, True):
        remaining = columns - row_width(top_parts(minimum_bar, compact))
        if remaining >= 0:
            emit(top_parts(minimum_bar + remaining, compact), columns)
            break
    else:
        emit(top_parts(minimum_bar, True), columns)

    for compact in (False, True):
        cost_part = cost.replace("估算 $", "估算$") if compact else cost
        bottom = [quota(minimum_bar, compact) for quota in quotas] + [cost_part]
        remaining = columns - row_width(bottom)
        if remaining >= 0:
            first, second = divmod(remaining, 2)
            emit([quotas[0](minimum_bar + first + second, compact),
                  quotas[1](minimum_bar + first, compact), cost_part], columns)
            break
    else:
        emit([quota(minimum_bar, True) for quota in quotas] + [cost_part], columns)


def main():
    data = json.load(sys.stdin)
    columns = terminal_width()
    now = time.time()

    model = data.get("model") or {}
    model_text = color(clean(model.get("display_name") or model.get("id") or "模型待更新"), "teal")
    effort = (data.get("effort") or {}).get("level")
    if effort:
        model_text += color(" · " + clean(effort), "purple")

    context = data.get("context_window") or {}
    usage = context.get("current_usage")
    total = None
    if isinstance(usage, dict):
        counts = [number(usage.get(key)) for key in (
            "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")]
        if all(value is not None for value in counts):
            total = sum(counts)
    compact = compact_window()
    limit = compact or number(context.get("context_window_size"))
    suffix = "窗" if compact else ""
    percent = 100 * total / limit if total is not None and limit else None
    context_color = "red" if percent is not None and percent >= 90 else "yellow" if percent is not None and percent >= 70 else "green"

    def context_part(size, compact=False):
        counts = (tokens(total) if total is not None else "—") + "/" + (tokens(limit) if limit else "—") + suffix
        pct = f"{percent:.0f}%" if percent is not None else "—"
        progress = bar(percent, size, context_color) if size else ""
        if compact:
            return color("上下文 ", context_color) + progress + color(f"{counts} {pct}", context_color)
        return color("上下文: ", context_color) + progress + color(f" {counts} ({pct})", context_color)

    cache = data.get("prompt_cache") or {}
    ratio = number(cache.get("hit_ratio"))
    if ratio is not None:
        cache_text = f"缓存 {ratio * 100:.0f}%"
    else:
        cache_text = "缓存 —"
    expires = number(cache.get("expires_at"))
    if cache.get("warm") and expires is not None and expires > now:
        remaining_seconds = math.ceil(expires - now)
        minutes, seconds = divmod(remaining_seconds, 60)
        cache_text += f" 余{minutes:02d}:{seconds:02d}"
    elif expires is not None and expires <= now:
        cache_text += " 已过期"
    elif "warm" in cache:
        cache_text += " 到期未知" if cache["warm"] else " 冷"

    rate = data.get("rate_limits") or {}
    quotas = []
    for key, label in (("five_hour", "5小时"), ("seven_day", "本周")):
        window = rate.get(key) or {}
        pct = number(window.get("used_percentage"))
        reset = number(window.get("resets_at"))
        if reset is not None and reset <= now:
            pct, reset = None, None

        def quota_part(size, compact=False, pct=pct, reset=reset, label=label):
            percent_text = f"{pct:.0f}%" if pct is not None else "—"
            progress = bar(pct, size, "blue") if size else ""
            if compact:
                return (color(label, "blue") + progress + color(percent_text, "blue") +
                        color(" 重置" + countdown(reset, now), "dim"))
            return (color(label + " ", "blue") + progress +
                    color(" " + percent_text, "blue") +
                    color(" · 重置 " + countdown(reset, now), "dim"))

        quotas.append(quota_part)
    estimate = number((data.get("cost") or {}).get("total_cost_usd"))
    cost_text = color(f"估算 ${estimate:.2f}" if estimate is not None else "估算 —", "yellow")
    speed_error = False
    try:
        measurement = output_rate(data.get("transcript_path"))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        # Keep the other live fields visible, but make the degraded metric clear.
        print(f"statusline-zh: speed unavailable: {type(error).__name__}: {error}", file=sys.stderr)
        measurement = None
        speed_error = True
    layout(model_text, context_part, color(cache_text, "blue"), quotas, cost_text, columns,
           measurement["tps"] if measurement else None, speed_error)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, AttributeError) as error:
        print("状态栏：数据读取失败")
        print(f"statusline-zh: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
