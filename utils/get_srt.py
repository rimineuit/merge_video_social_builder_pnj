"""
Hàm để chuyển file .wav thành .srt và lưu ra file.
"""

from google import genai
import os

def get_srt_from_wav_file(api_key=None, file_path="audio/output.wav"):
    client = genai.Client(api_key=api_key)

    # Upload file audio
    myfile = client.files.upload(file=file_path)

    # Prompt mô tả rõ ràng
    prompt = """
    Transcribe this audio file into a valid .srt subtitle file (word by word).

    🧩 Requirements:
    - Each subtitle block must include:
    1️⃣ Subtitle index number (starting from 1)
    2️⃣ Time range in the format HH:MM:SS,mmm --> HH:MM:SS,mmm  (use commas, not dots)
    3️⃣ One word per block (word-level transcription)
    4️⃣ Separate each block with a blank line

    📘 Example output:
    1
    00:00:00,199 --> 00:00:00,529
    Kính

    2
    00:00:00,529 --> 00:00:00,769
    chào

    3
    00:00:00,769 --> 00:00:01,049
    quý

    4
    00:00:01,049 --> 00:00:01,319
    vị.

    ⚠️ Only output the .srt content — no explanations, comments, or additional text.
    """


    # ✅ Truyền đúng dạng: text + file
    response = client.models.generate_content(
    model='gemini-2.5-pro',
    contents=[prompt, myfile]
    )
    srt_text = response.text.strip()

    # # ✅ Lưu ra file .srt
    # base_name = os.path.splitext(file_path)[0]
    # output_path = f"{base_name}.srt"
    # with open(output_path, "w", encoding="utf-8") as f:
    #     f.write(srt_text)

    # print(f"✅ SRT file saved to: {output_path}")
    return srt_text


if __name__ == "__main__":
    import sys
    api_key = sys.argv[1] if len(sys.argv) > 1 else "AIzaSyCIXYIVHYMXgJu8jqb5pLVgE47TEBtnJk0"
    file_path = sys.argv[2] if len(sys.argv) > 2 else "audio/output.wav"

    srt_text = get_srt_from_wav_file(api_key, file_path)
    print("\n--- SRT CONTENT ---\n")
    print(srt_text)
