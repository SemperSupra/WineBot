
from .models import Event


class SubtitleGenerator:
    def __init__(self, events: list[Event]):
        self.events = sorted(events, key=lambda e: e.t_rel_ms)

    def _ms_to_vtt(self, ms: int) -> str:
        seconds = ms // 1000
        millis = ms % 1000
        minutes = seconds // 60
        hours = minutes // 60
        minutes %= 60
        seconds %= 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"

    def _ms_to_ass(self, ms: int) -> str:
        seconds = ms // 1000
        millis = ms % 1000
        minutes = seconds // 60
        hours = minutes // 60
        minutes %= 60
        seconds %= 60
        centis = millis // 10
        return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"

    def generate_vtt(self) -> str:
        lines = ["WEBVTT", ""]

        for i, event in enumerate(self.events):
            start = self._ms_to_vtt(event.t_rel_ms)
            # Default duration 2s if not last event, else until next event
            if i < len(self.events) - 1:
                end_ms = self.events[i + 1].t_rel_ms
                # Cap max duration for single event to avoid clutter, unless it's a persistent state?
                # For simplicity, let's just show it until the next event or +3s
                end_ms = min(event.t_rel_ms + 3000, end_ms)
                end = self._ms_to_vtt(end_ms)
            else:
                end = self._ms_to_vtt(event.t_rel_ms + 3000)

            lines.append(f"{start} --> {end}")
            lines.append(f"[{event.kind.upper()}] {event.message}")
            lines.append("")

        return "\n".join(lines)

    def generate_ass(self, width: int, height: int) -> str:
        header = f"""[Script Info]
Title: WineBot Session
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,1,1,2,10,10,10,1
Style: Overlay,Arial,20,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        lines = [header.strip()]

        for i, event in enumerate(self.events):
            start = self._ms_to_ass(event.t_rel_ms)
            if i < len(self.events) - 1:
                end_ms = min(event.t_rel_ms + 3000, self.events[i + 1].t_rel_ms)
                end = self._ms_to_ass(end_ms)
            else:
                end = self._ms_to_ass(event.t_rel_ms + 3000)

            # Basic subtitle line
            text = f"[{event.kind.upper()}] {event.message}"
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

            # Overlay handling
            if event.pos:
                # x, y, w, h
                x = event.pos.get("x", 0)
                y = event.pos.get("y", 0)
                # We can use \pos(x,y)
                # If we want a box, we can draw a rectangle using drawing commands, but that's complex.
                # Let's just place the text at x,y.
                # Alignment 7 is top-left.

                # Check for explicit style overrides
                if event.style:
                    if "color" in event.style:
                        # Convert #RRGGBB to &HBBGGRR&
                        pass

                overlay_text = event.message
                if event.kind == "annotation" and event.pos:
                    lines.append(
                        rf"Dialogue: 1,{start},{end},Overlay,,0,0,0,,{{\pos({x},{y})}}{overlay_text}"
                    )

        return "\n".join(lines)
