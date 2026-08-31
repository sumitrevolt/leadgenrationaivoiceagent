from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip
import os

# Configuration
OUTPUT_DIR = "data/content_gen"
VIDEO_OUTPUT = os.path.join(OUTPUT_DIR, "final_video.mp4")

def render_video(voice_path, image_path, output_path=VIDEO_OUTPUT):
    """
    Creates a simple video with a static background image and synced voiceover.
    This is the core rendering node logic.
    """
    print("Loading assets...")
    audio = AudioFileClip(voice_path)
    # Using a placeholder image for now - in production, this is where SDXL images go.
    # User needs to ensure an image file exists.
    image = ImageClip(image_path).set_duration(audio.duration)
    
    video = image.set_audio(audio)
    
    # Write the video file
    print("Rendering video...")
    video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")
    print(f"Video rendered at: {output_path}")

if __name__ == "__main__":
    # Ensure these exist before running
    v_path = os.path.join(OUTPUT_DIR, "voiceover.mp3")
    i_path = os.path.join(OUTPUT_DIR, "background.png") 
    
    if os.path.exists(v_path) and os.path.exists(i_path):
        render_video(v_path, i_path)
    else:
        print("Missing assets! Ensure voiceover.mp3 and background.png exist in data/content_gen/")
