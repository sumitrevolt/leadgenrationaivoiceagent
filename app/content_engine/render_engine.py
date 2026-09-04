import os
import subprocess

# Configuration
OUTPUT_DIR = "data/content_gen"
VIDEO_OUTPUT = os.path.join(OUTPUT_DIR, "final_video.mp4")


def get_video_codec() -> str:
    """Detect available FFmpeg encoder codec: NVENC GPU or libx264 CPU fallback."""
    try:
        res = subprocess.run(
            ["ffmpeg", "-encoders"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if "h264_nvenc" in res.stdout:
            return "h264_nvenc"
    except Exception:
        pass
    return "libx264"


def render_video(voice_path, image_path, output_path=VIDEO_OUTPUT):
    """
    Creates a video with background image and synced voiceover.
    Uses local NVIDIA GPU hardware acceleration (h264_nvenc) when available,
    falling back to libx264 CPU encoding.
    """
    codec = get_video_codec()
    print(f"Rendering video using codec: {codec}...")
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # 1. Fast Native FFmpeg (NVENC GPU / CPU)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-i", str(voice_path),
        "-c:v", codec,
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(output_path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode == 0:
            print(f"Video rendered successfully via FFmpeg ({codec}) at: {output_path}")
            return output_path
        print(f"FFmpeg {codec} returned non-zero ({res.returncode}), trying CPU fallback...")
    except Exception as e:
        print(f"FFmpeg {codec} exception: {e}")

    # Fallback to libx264 CPU if NVENC had an issue
    if codec != "libx264":
        cmd[cmd.index(codec)] = "libx264"
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if res.returncode == 0:
                print(f"Video rendered successfully via libx264 at: {output_path}")
                return output_path
        except Exception as e:
            print(f"libx264 fallback error: {e}")

    # 2. MoviePy Fallback (if installed)
    try:
        from moviepy.editor import AudioFileClip, ImageClip
        audio = AudioFileClip(voice_path)
        image = ImageClip(image_path).set_duration(audio.duration)
        video = image.set_audio(audio)
        video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac", threads=2)
        print(f"Video rendered via MoviePy at: {output_path}")
        return output_path
    except Exception as e:
        print(f"MoviePy fallback error: {e}")

    return None


if __name__ == "__main__":
    # Ensure these exist before running
    v_path = os.path.join(OUTPUT_DIR, "voiceover.mp3")
    i_path = os.path.join(OUTPUT_DIR, "background.png")

    if os.path.exists(v_path) and os.path.exists(i_path):
        render_video(v_path, i_path)
    else:
        print("Missing assets! Ensure voiceover.mp3 and background.png exist in data/content_gen/")
