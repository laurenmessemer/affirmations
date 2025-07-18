from flask import Flask, request, jsonify
import requests
import os
import boto3
from moviepy.editor import AudioFileClip, CompositeAudioClip
import uuid
import mimetypes

mimetypes.add_type('audio/mpeg', '.mp3')

app = Flask(__name__)

# --- AWS Upload ---
def upload_to_s3(file_path, bucket, key):
    s3 = boto3.client("s3")
    s3.upload_file(
        Filename=file_path,
        Bucket=bucket,
        Key=key,
        ExtraArgs={
            "ContentType": "audio/mpeg"
        }
    )
    return f"https://{bucket}.s3.amazonaws.com/{key}"

# --- Download Helper ---
def download_file(url, filename):
    r = requests.get(url)
    with open(filename, 'wb') as f:
        f.write(r.content)
    return filename

# --- Main Audio Handler ---
def handler(event):
    response_id = event["response_id"]
    voice_urls = event["voice_urls"]
    background_url = event["background_music_url"]

    os.makedirs("/tmp", exist_ok=True)
    uid = str(uuid.uuid4())[:8]

    # Download background music
    bg_path = f"/tmp/bg_{uid}.mp3"
    download_file(background_url, bg_path)

    # Download voices
    voice_paths = []
    for i, url in enumerate(voice_urls):
        path = f"/tmp/voice_{i+1}_{uid}.mp3"
        download_file(url, path)
        voice_paths.append(path)

    # Load audio clips
    background = AudioFileClip(bg_path).volumex(0.4)
    voice_clips = [AudioFileClip(p).volumex(1.0) for p in voice_paths]

    # Stagger 7 loops of voices
    overlays = []
    loop_count = 7
    delay_increment = 2.5  # seconds between starts

    for i in range(loop_count):
        for j, voice in enumerate(voice_clips):
            delay = (i * len(voice_clips) + j) * delay_increment
            overlays.append(voice.set_start(delay))

    max_duration = max(c.end for c in overlays)
    combined = CompositeAudioClip([background.set_duration(max_duration)] + overlays)

    # Write output
    local_output = f"/tmp/final_{response_id}_{uid}.mp3"
    combined.write_audiofile(local_output, fps=44100)

    return {
        "response_id": response_id,
        "uid": uid,
        "local_path": local_output,
        "filename": os.path.basename(local_output)
    }

# --- API Endpoint ---
@app.route("/generate-audio", methods=["POST"])
def generate_audio():
    try:
        event = request.get_json()
        result = handler(event)

        s3_bucket = "affirmation.maker.media"
        s3_key = f"final_audio/{result['filename']}"
        s3_url = upload_to_s3(result["local_path"], s3_bucket, s3_key)

        return jsonify({
            "status": "success",
            "audio_url": s3_url
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
