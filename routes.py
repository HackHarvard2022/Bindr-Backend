from flask import Flask
from flask import request

app = Flask(__name__)
@app.route('/get_transcription', methods=['GET'])
def get_transcription():
    url = request.args.get('url')
    bookmarks = request.args.get('bookmarks')
    time_interval = int(request.args.get('time_interval'))
    ret = transcribe_from_link(url, bookmarks, time_interval, True)
    transcription, words_in_interval = ret
    print(transcription, words_in_interval)

    return (transcription, words_in_interval)

from typing import DefaultDict
import requests
import youtube_dl
import aiohttp
import asyncio
from time import sleep
import collections
# 1cf2493653334fe4b8e9d7bd971f1d41
auth_key = '1e60880ae392441d90d0905629c52711'
transcript_endpoint = "https://api.assemblyai.com/v2/transcript"
upload_endpoint = 'https://api.assemblyai.com/v2/upload'
headers_auth_only = {'authorization': auth_key}
headers = {
    "authorization": auth_key,
    "content-type": "application/json"
}

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'ffmpeg-location': './',
    'outtmpl': "./%(id)s.%(ext)s",
}

CHUNK_SIZE = 5242880

def transcribe_from_link(link, bookmarks, time_interval, categories: bool):
    _id = link.strip()
    def get_vid(_id):
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(_id)
    meta = get_vid(_id)
    save_location = meta['id'] + ".mp3"
    duration = meta['duration']
    print('Saved mp3 to', save_location)
    def read_file(filename):
        with open(filename, 'rb') as _file:
            while True:
                data = _file.read(CHUNK_SIZE)
                if not data:
                    break
                yield data
    
    upload_response = requests.post(
        upload_endpoint,
        headers=headers_auth_only, data=read_file(save_location)
    )

    audio_url = upload_response.json()['upload_url']
    print('Uploaded to', audio_url)
    transcript_request = {
        'audio_url': audio_url,
        'iab_categories': 'True' if categories else 'False',
    }

    transcript_response = asyncio.run(make_trascript_request(transcript_endpoint, transcript_request, headers))

    transcript_id = transcript_response['id']
    polling_endpoint = transcript_endpoint + "/" + transcript_id
    print("Transcribing at", polling_endpoint)
    polling_response = requests.get(polling_endpoint, headers=headers)
    while polling_response.json()['status'] != 'completed':
        sleep(30)
        try:
            polling_response = requests.get(polling_endpoint, headers=headers)
        except:
            print("Expected wait time:", duration*2/5, "seconds")
            print("After wait time is up, call poll with id", transcript_id)
            return transcript_id

    words_in_intervals = get_bookmarks(polling_response.json(), bookmarks, time_interval)
    transcription = ''.join(polling_response.json()['text'])

    return [transcription, words_in_intervals]

def get_bookmarks(transcript_response, bookmarks, input_range):
    time_elapsed = 0
    intervals = []
    input_range = int(input_range)
    bookmarks = bookmarks[1:-2].split(',')

    for i in bookmarks:
        i = int(i)

        start, end = i - input_range, i + input_range
        if start < 0:
            start = 0
        intervals.append((start, end))
    words_in_range = collections.defaultdict(list)

    for ind in range(len(intervals)):
        i_start, i_end = intervals[ind]
        for indx in range(len(transcript_response['words'])):
            d = transcript_response['words'][indx]
            text, start, end, confidence, speaker = d['text'], d['start'], d['end'], d['confidence'], d['speaker']
            if start >= i_end:
                break
            if int(i_start) <= start and start <= i_end:
                # can get append as tuple (text, start) to get word timestamps
                words_in_range[ind].append(text)

            time_elapsed = end
    words_in_intervals = []
    for i in range(len(words_in_range)):
        words_in_intervals.append(' '.join(words_in_range[i]))
    return words_in_intervals

async def make_trascript_request(transcript_endpoint, transcript_request, headers):
    async with aiohttp.ClientSession() as session:
        async with session.post(transcript_endpoint, json=transcript_request, headers=headers) as resp:
            res = await resp.json()
    return res
params = {
    "url": "https://www.youtube.com/watch?v=D7KByPTU8Xg",
    "bookmarks": [10000,20000,30000],
    "time_interval": 10000
    }

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=105)
