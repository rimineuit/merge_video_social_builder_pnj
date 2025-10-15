import srt

def convert_srt_to_json(srt_text):
    # with open(file_path, "r", encoding="utf-8") as f:
    #     srt_text = f.read()

    subtitles = list(srt.parse(srt_text))
    tmp_list = []
    for sub in subtitles:
        tmp_list.append({
            "index": sub.index,
            "start": round(sub.start.total_seconds(), 3),  # giây float
            "end": round(sub.end.total_seconds(), 3),      # giây float
            "content": sub.content
        })
    return tmp_list
        
# import sys
# if __name__=="__main__":
#     file_path = sys.argv[1] if len(sys.argv) > 2 else "audio/output.srt"
#     print(convert_srt_to_json(file_path=file_path))
    