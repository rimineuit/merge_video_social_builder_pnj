from fastapi import HTTPException, FastAPI
from pydantic import BaseModel, Field, HttpUrl, conint, field_validator, model_validator
from typing import List
from pathlib import Path
from fastapi.responses import JSONResponse
import subprocess, json, sys, os, shutil, re

# --- GCS upload ---
def upload_to_gcs(local_path: str, dest_blob_name: str, make_public: bool = False) -> str:
    """
    Upload local_path -> gs://{GCP_BUCKET_NAME}/{dest_blob_name}
    Trả về public URL (nếu make_public) hoặc media link mặc định của blob.
    """
    from google.cloud import storage

    bucket_name = os.getenv("GCP_BUCKET_NAME")
    if not bucket_name:
        raise RuntimeError("Thiếu biến môi trường GCP_BUCKET_NAME.")

    client = storage.Client()  # ADC (Cloud Run/Workload Identity) / hoặc SA JSON khi dev local
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(dest_blob_name)
    blob.upload_from_filename(local_path, content_type="video/mp4")

    if make_public or os.getenv("MAKE_PUBLIC", "").lower() in {"1", "true", "yes"}:
        try:
            blob.make_public()
        except Exception:
            # Nếu bucket không cho phép public, vẫn trả về blob.public_url (có thể không truy cập được)
            pass

    # public_url sẽ là https://storage.googleapis.com/{bucket}/{object}
    return blob.public_url

# --- Models ---
class MakeVideoRequest(BaseModel):
    transcripts: List[str] = Field(..., min_length=1)
    wav_urls: List[HttpUrl] = Field(..., min_length=1)
    image_urls: List[HttpUrl] = Field(..., min_length=1)
    fps: conint(ge=10, le=60) = Field(30)
    show_script: bool = Field(False)
    id: str

    @field_validator("transcripts")
    @classmethod
    def _clean_transcripts(cls, v: List[str]) -> List[str]:
        cleaned = [s.strip() for s in v]
        if any(len(s) == 0 for s in cleaned):
            raise ValueError("Mọi transcript phải khác rỗng sau khi strip.")
        return cleaned

    @model_validator(mode="after")
    def _lengths_must_match(self):
        if not (len(self.transcripts) == len(self.wav_urls) == len(self.image_urls)):
            raise ValueError(
                f"Số phần tử không khớp: transcripts={len(self.transcripts)}, "
                f"wav_urls={len(self.wav_urls)}, image_urls={len(self.image_urls)}."
            )
        return self

# --- Utils dọn rác an toàn ---
def safe_rmtree(p: str):
    try:
        shutil.rmtree(p, ignore_errors=True)
    except Exception:
        pass

def safe_unlink(p: str):
    try:
        Path(p).unlink(missing_ok=True)
    except Exception:
        pass

app = FastAPI()

@app.post("/generate-video")
def generate_video(body: MakeVideoRequest):
    transcripts = body.transcripts
    wav_urls = [str(u) for u in body.wav_urls]
    image_urls = [str(u) for u in body.image_urls]
    fps = body.fps
    show_script = body.show_script

    # Chạy script ghép video
    cmd = [
        sys.executable,"-m", 
        "video_maker.concat_video",
        json.dumps(transcripts, ensure_ascii=False),
        json.dumps(wav_urls, ensure_ascii=False),
        json.dumps(image_urls, ensure_ascii=False),
        str(fps),
        str(show_script),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=9000,
            check=True,  # raise CalledProcessError nếu exit code != 0
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Script error: {e.stderr or e.stdout}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Tạo video quá thời gian (timeout).")

    # File đầu ra mặc định từ script
    default_out = Path("audio/my_video.mp4")
    if not default_out.exists():
        raise HTTPException(status_code=500, detail="Không tìm thấy file đầu ra 'audio/my_video.mp4'.")

    # Chuẩn hóa id để đặt tên file/object an toàn
    safe_id = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", body.id).strip("_") or "video"
    final_local = Path("audio") / f"{safe_id}.mp4"

    # Đổi tên file local theo id
    try:
        if final_local.exists():
            final_local.unlink()
        shutil.move(str(default_out), str(final_local))
    except Exception as e:
        # Nếu move lỗi thì vẫn dùng default_out
        final_local = default_out

    # Upload lên GCS: videos/{id}.mp4
    dest_object = f"{safe_id}.mp4"
    try:
        video_url = upload_to_gcs(str(final_local), dest_object)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload GCS lỗi: {e}")

    # Tuỳ chọn: dọn tài nguyên tạm (nếu script tạo thư mục/âm thanh/ảnh phụ)
    safe_unlink("bg.wav")
    safe_rmtree("./script")
    safe_rmtree("./audio")  # cẩn thận: nếu xóa 'audio' sẽ mất file out; chỉ xóa nếu không cần giữ local
    safe_rmtree("./image")

    # Trả về URL (JSON)
    return JSONResponse({"url": video_url})
