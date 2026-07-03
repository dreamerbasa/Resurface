from youtube_transcript_api import YouTubeTranscriptApi
#https://www.youtube.com/watch?v=rKgtm81yi94
try:
    api = YouTubeTranscriptApi()
    result = api.fetch("rKgtm81yi94")
    print("SUCCESS:", [s.text for s in result.snippets[:3]])
except Exception as e:
    print("ERROR:", type(e).__name__, str(e))
