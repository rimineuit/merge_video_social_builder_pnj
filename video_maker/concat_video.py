import os
from natsort import natsorted
from moviepy import AudioFileClip, TextClip, ColorClip, ImageClip, CompositeVideoClip, vfx, afx
from utils.get_srt import get_srt_from_wav_file
from utils.convert_srt_file_to_json import convert_srt_to_json
from pydub import AudioSegment
import requests
import shutil

# Lưu transcripts
def save_transcripts_to_folder(transcripts: list[str], output_folder='./script'):
    os.makedirs(output_folder, exist_ok=True)
    for i, s in enumerate(transcripts):
        file_path = os.path.join(output_folder, f"{i+1}.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(s)

# Download wav files from URLs
def download_wavs_from_urls(wav_urls, audio_dir='./audio'):
    os.makedirs(audio_dir, exist_ok=True)
    for i, url in enumerate(wav_urls):
        file_name = os.path.join(audio_dir, f"{i+1}.wav")
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open(file_name, 'wb') as f:
            f.write(r.content)

# Download images from URLs
def download_images_from_urls(image_urls, image_dir='./image'):
    os.makedirs(image_dir, exist_ok=True)
    for i, url in enumerate(image_urls):
        file_name = os.path.join(image_dir, f"{i+1}.png")
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open(file_name, 'wb') as f:
            f.write(r.content)

# Lấy .srt từ file wav và trả về đầu ra cho giai đoạn tạo scripts
def generate_transcripts(file_path="audio/output.wav"):
    srt_text = get_srt_from_wav_file(api_key="AIzaSyCIXYIVHYMXgJu8jqb5pLVgE47TEBtnJk0",file_path=file_path)
    json_data = convert_srt_to_json(srt_text)
    return json_data

# Tạo video
def make_video(script_dir='./script', audio_dir='./audio', image_dir='./image', fps=30, show_script=False, font="font/Roboto-SemiBold.ttf"):
    """
    Tạo video từ ảnh + audio + transcript.
    Các vá quan trọng:
    - merge_audio dùng pydub (chuẩn hoá format + overlay bg mượt)
    - get_durations bằng pydub
    - Ép ảnh về kích thước cố định trước khi zoom
    - Fade audio tổng (không dùng AudioFade trên clip video)
    """
    output_video = os.path.join(audio_dir, 'my_video.mp4')
    output_wav = os.path.join(audio_dir, 'output.wav')

    # Kích thước khung video thống nhất để tránh resample nặng
    VIDEO_SIZE = (1080, 1920)  # đổi thành (1920,1080) nếu muốn landscape

    # ----- A) MERGE AUDIO bằng pydub (ổn định) -----
    def merge_audio(audio_dir=audio_dir, silence=0.5, ouput_wav=output_wav, bg_wav_path="bg.wav"):
        """
        Gộp các wav thoại, chèn im lặng 0.5s, overlay nhạc nền nếu có, fade biên.
        Tất cả chuẩn hoá về 16-bit, mono, 24000 Hz (đổi nếu cần).
        """
        TARGET_SR = 24000
        TARGET_CH = 1
        TARGET_SW = 2   # 16-bit

        wav_files = natsorted([os.path.join(audio_dir, f) for f in os.listdir(audio_dir) if f.endswith('.wav')])
        if not wav_files:
            raise RuntimeError("Không tìm thấy WAV nào trong thư mục audio.")

        def _norm(seg: AudioSegment) -> AudioSegment:
            seg = seg.set_frame_rate(TARGET_SR).set_channels(TARGET_CH).set_sample_width(TARGET_SW)
            return seg.apply_gain(-1.0)  # headroom nhỏ

        parts = []
        for i, f in enumerate(wav_files):
            seg = AudioSegment.from_file(f)
            seg = _norm(seg)
            parts.append(seg)
            if i < len(wav_files) - 1:
                parts.append(AudioSegment.silent(duration=int(silence * 1000)))

        main = sum(parts) if parts else AudioSegment.silent(duration=1)

        # overlay nhạc nền nếu có
        if os.path.exists(bg_wav_path):
            try:
                bg = AudioSegment.from_file(bg_wav_path)
                bg = _norm(bg).apply_gain(-14.0)  # nền nhỏ
                loops = (len(main) // len(bg)) + 1
                bg_full = (bg * loops)[:len(main)]
                bg_full = bg_full.fade_in(400).fade_out(600)
                mixed = main.overlay(bg_full)
            except Exception:
                mixed = main
        else:
            mixed = main

        mixed = mixed.fade_in(50).fade_out(120)
        os.makedirs(os.path.dirname(ouput_wav), exist_ok=True)
        mixed.export(ouput_wav, format="wav")

    # ----- B) Durations của từng đoạn bằng pydub -----
    def get_durations(audio_dir):
        durations = []
        wav_files = natsorted([os.path.join(audio_dir, f) for f in os.listdir(audio_dir) if f.endswith('.wav')])
        for f in wav_files:
            seg = AudioSegment.from_file(f)
            durations.append(len(seg) / 1000.0)
        return durations


    def build_bg_to_length(bg_wav_path: str, target_seconds: float, out_path: str,
                        crossfade_ms: int = 200,
                        target_sr: int = 24000, target_ch: int = 1, target_sw: int = 2):
        """
        Tạo nhạc nền dài đúng target_seconds bằng cách LOOP nhạc gốc với crossfade.
        - crossfade_ms: 0..500ms thường là ổn (tuỳ beat).
        - target_sr/ch/sw: chuẩn hoá format để khớp với audio thoại (tránh giật).
        """
        if not os.path.exists(bg_wav_path):
            raise FileNotFoundError(f"Không tìm thấy file nhạc nền: {bg_wav_path}")

        bg = AudioSegment.from_file(bg_wav_path)
        # chuẩn hoá format
        bg = bg.set_frame_rate(target_sr).set_channels(target_ch).set_sample_width(target_sw)

        target_ms = int(round(target_seconds * 1000))
        if target_ms <= 0:
            raise ValueError("target_seconds phải > 0")

        # Nếu nhạc gốc đã đủ dài -> chỉ cần cắt
        if len(bg) >= target_ms:
            out = bg[:target_ms]
            out.export(out_path, format="wav")
            return out_path

        # Loop cho đủ độ dài, nối với crossfade để mượt
        parts = []
        current = AudioSegment.silent(duration=0, frame_rate=bg.frame_rate)
        while len(current) < target_ms:
            if len(current) == 0 or crossfade_ms <= 0:
                current += bg
            else:
                current = current.append(bg, crossfade=crossfade_ms)

        out = current[:target_ms]
        # Fade nhẹ đầu/cuối để tránh click
        out = out.fade_in(200).fade_out(300)
        out.export(out_path, format="wav")
        return out_path
    
    # Tính tổng thời lượng để khớp nhạc nền
    durations = get_durations(audio_dir)
    sum_durations = sum(durations) + len(durations) * 0.5  # 0.5s im lặng giữa các đoạn

    # TẠO bg.wav đủ dài bằng cách loop, thay cho cut_wav_from_start(...)
    build_bg_to_length("base_audio/background.wav", sum_durations, "bg.wav", crossfade_ms=200)

    # Merge lời + nhạc nền -> output_wav
    merge_audio()

    # Audio cuối cùng + fade
    audio_clip = AudioFileClip(output_wav)
    # audio_clip = audio_clip.audio_fadein(0.5).audio_fadeout(0.8)

    # ----- E) Load ảnh -----
    img_clip = []
    for i in natsorted(os.listdir(image_dir)):
        if i.endswith('.png'):
            # ép size để tránh resample nặng từng frame
            img = ImageClip(os.path.join(image_dir, i))
            img_clip.append(img)

    # ----- F) Dựng timeline -----
    final_clips = []
    tmp = 0.0
    for i in range(len(img_clip)):
        dur = durations[i] + 0.5  # khớp khoảng silence giữa các đoạn
        # Zoom ảnh 
        base = img_clip[i].with_start(tmp).with_duration(dur) \
                          .resized(lambda t: 1 + 0.04 * t) \
                          .with_effects([vfx.FadeIn(0.5), vfx.FadeOut(0.5)]) \
                          .with_position(("center", "center"))
                          
        final_clips.append(base)
        tmp += dur

    # ----- D) Load transcript clips -----
    if show_script:
        scripts_json = generate_transcripts(file_path="audio/output.wav")
        # script_clip = []
        # bg_clips = []
        for script in scripts_json:
            content = script['content']
            start = script['start']
            end = script['end']
            # import textwrap
            # wrapped_text = "\n".join(textwrap.wrap(content, width=5))
            txt = TextClip(
                text=content,
                font=font,
                font_size=60,
                color='red',
                text_align='center',
                method='caption',
                horizontal_align="center",
                vertical_align="bottom",
                size=(500, None),
                margin=(5, 30)
            )
            bg = ColorClip(size=txt.size, color=(0, 0, 0)).with_opacity(0.7)
            
            out_scr = txt.with_start(start).with_end(end) \
                                .with_effects([vfx.CrossFadeIn(0.1), vfx.CrossFadeOut(0.1)]) \
                                .with_position(("center", "center"))
                                
            # out_bg = bg.with_start(start).with_end(end) \
            #                 .with_effects([vfx.CrossFadeIn(0.1), vfx.CrossFadeOut(0.1)]) \
            #                 .with_position(("center", "center"))
                                
            final_clips.append(out_scr)
            # final_clips.append(out_bg)

    final_video = CompositeVideoClip(final_clips).with_audio(audio_clip)

    # ----- G) Ghi file với tham số encode ổn định -----
    final_video.write_videofile(
        output_video,
        fps=fps,                    # 24 hoặc 30
        codec="libx264",
        audio_codec="aac",
        preset="slow",            # "slow" mượt hơn nhưng lâu hơn
        bitrate="5000k",
        threads=4
    )
        
def delete_resource(script_dir='./script', audio_dir='./audio', image_dir='./image'):
    if os.path.exists(script_dir) and os.path.isdir(script_dir):
        shutil.rmtree(script_dir)
    if os.path.exists(audio_dir) and os.path.isdir(audio_dir):
        shutil.rmtree(audio_dir)
    if os.path.exists(image_dir) and os.path.isdir(image_dir):
        shutil.rmtree(image_dir)

def main(transcripts, wav_urls, image_urls, fps=30, show_script=False):
    delete_resource()
    save_transcripts_to_folder(transcripts)
    download_wavs_from_urls(wav_urls)
    download_images_from_urls(image_urls)
    make_video(fps=fps, show_script=show_script)
    
import sys
if __name__ == "__main__":
    import json
    if len(sys.argv) < 6:
        print("Usage: python make_video_from_image.py <transcripts_json> <wav_urls_json> <image_urls_json> <fps> <show_script>")
        sys.exit(1)

    transcripts = json.loads(sys.argv[1])
    wav_urls = json.loads(sys.argv[2])
    image_urls = json.loads(sys.argv[3])
    fps = int(sys.argv[4])
    show_script = sys.argv[5].lower() in ("true", "1", "yes")

    main(transcripts, wav_urls, image_urls, fps=fps, show_script=show_script)
