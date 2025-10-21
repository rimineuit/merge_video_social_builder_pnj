from moviepy import VideoFileClip

clip = VideoFileClip("audio/string.mp4")
first_frame = clip.get_frame(0.1)   # frame tại thời điểm 0 giây
clip.close()
from PIL import Image

Image.fromarray(first_frame).save("first_frame.jpg")

