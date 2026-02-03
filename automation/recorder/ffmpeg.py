import subprocess
import os
import signal
import time
import logging

logger = logging.getLogger(__name__)

class FFMpegRecorder:
    def __init__(self, display: str, resolution: str, fps: int, output_file: str):
        self.display = display
        self.resolution = resolution
        self.fps = fps
        self.output_file = output_file
        self.process = None

    def start(self):
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "x11grab",
            "-draw_mouse", "1",
            "-r", str(self.fps),
            "-s", self.resolution,
            "-i", self.display,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            self.output_file
        ]
        
        logger.info(f"Starting ffmpeg: {' '.join(cmd)}")
        
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )

    def stop(self):
        if not self.process:
            return

        logger.info("Stopping ffmpeg...")
        try:
            self.process.terminate()
        except ProcessLookupError:
            self.process = None
            return
        
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg didn't stop, killing...")
            self.process.kill()
            self.process.wait()
            
        self.process = None

    def mux_subtitles(self, ass_file: str, vtt_file: str, metadata: dict = None):
        """Embeds external subtitle files into the MKV container with global metadata."""
        if not os.path.exists(self.output_file):
            logger.error(f"Cannot mux: {self.output_file} not found.")
            return

        temp_output = self.output_file + ".muxed.mkv"
        
        cmd = [
            "ffmpeg", "-y",
            "-i", self.output_file,
            "-i", ass_file,
            "-i", vtt_file,
            "-map", "0:v",
            "-map", "1:s",
            "-map", "2:s",
            "-c", "copy",
            "-metadata:s:s:0", "title=Overlays (ASS)",
            "-metadata:s:s:1", "title=Events (VTT)",
            "-disposition:s:0", "default",
        ]

        if metadata:
            for key, value in metadata.items():
                if value:
                    cmd.extend(["-metadata", f"{key}={value}"])
        
        cmd.append(temp_output)
        
        logger.info(f"Muxing subtitles and metadata: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            os.replace(temp_output, self.output_file)
            logger.info("Subtitles successfully embedded in MKV.")
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode()
            logger.error(f"Failed to mux subtitles: {err}")
            if os.path.exists(temp_output):
                os.remove(temp_output)
