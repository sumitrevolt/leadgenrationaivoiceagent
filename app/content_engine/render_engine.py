import os

from moviepy.editor import AudioFileClip, CompositeVideoClip, ImageClip, TextClip

# Configuration
OUTPUT_DIR = "data/content_gen"
VIDEO_OUTPUT = os.path.join(OUTPUT_DIR, "final_video.mp4")

def get_video_codec() -> str:
    """Detect available FFmpeg encoder codec: NVENC GPU or libx264 CPU fallback."""
    try:
        import subprocess

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
    Uses GPU hardware acceleration (h264_nvenc) when available, fallback to libx264 CPU.
    """
    print("Loading assets...")
    audio = AudioFileClip(voice_path)
    image = ImageClip(image_path).set_duration(audio.duration)
    video = image.set_audio(audio)

    codec = get_video_codec()
    print(f"Rendering video using codec: {codec}...")
    try:
        video.write_videofile(
            output_path, fps=24, codec=codec, audio_codec="aac", threads=4
        )
    except Exception as e:
        print(f"Codec {codec} failed ({e}), falling back to libx264...")
        video.write_videofile(
            output_path, fps=24, codec="libx264", audio_codec="aac", threads=2
        )
    print(f"Video rendered at: {output_path}")

if __name__ == "__main__":
    # Ensure these exist before running
    v_path = os.path.join(OUTPUT_DIR, "voiceover.mp3")
    i_path = os.path.join(OUTPUT_DIR, "background.png")

    if os.path.exists(v_path) and os.path.exists(i_path):
        render_video(v_path, i_path)
    else:
        print("Missing assets! Ensure voiceover.mp3 and background.png exist in data/content_gen/")
