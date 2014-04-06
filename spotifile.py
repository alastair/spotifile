#!/usr/bin/env python

from __future__ import unicode_literals

import sys
import threading
import wave
from cStringIO import StringIO
import Queue
import spotifyfs
import spotipy
import spotify
import requests
import conf


messages = Queue.Queue()
response = Queue.Queue()
trackqueue = Queue.Queue()

# Assuming a spotify_appkey.key in the current dir
session = spotify.Session()

# Process events in the background
loop = spotify.EventLoop(session)
loop.start()

# Events for coordination
logged_in = threading.Event()
end_of_track = threading.Event()

spotify_ios = {}
spotify_wavs = {}
# { playlistid: {"tracks": [..], "coverart": url} }
metadata = {}
playlists = {}
current_track = None


def on_logged_in(session, error_type):
    assert error_type == spotify.ErrorType.OK, 'Login failed'
    logged_in.set()

def on_end_of_track(self):
    end_of_track.set()

def on_consume(session, format, frames, num_frames):
    print "got", num_frames, "frames"
    thewav = spotify_wavs[current_track]
    thewav.writeframesraw(frames)
    return num_frames


# Register event listeners
session.on(spotify.SessionEvent.LOGGED_IN, on_logged_in)
session.on(spotify.SessionEvent.END_OF_TRACK, on_end_of_track)
session.on(spotify.SessionEvent.MUSIC_DELIVERY, on_consume)

# Assuming a previous login with remember_me=True and a proper logout
session.login(conf.username, conf.password)

logged_in.wait()

# TODO Get rid of this sleep
import time
time.sleep(1)

def open_new_file(trid, duration):
    # Always add 1 second to make up for unmatching samples/length
    duration += 1

    io = StringIO()
    w = wave.open(io, "w")
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(44100)
    frames = duration * 44100
    w.setnframes(frames)

    header_size = 44
    size = header_size + (44100 * 4 * duration)

    spotify_ios[trid] = io
    spotify_wavs[trid] = w
    return size

def load_playlist(plid):
    print "loadingplaylist", plid
    p = session.get_playlist(plid).load()
    tracks = {}
    for t in p.tracks:
        name = "%s - %s - %s.wav" % (t.index, t.artists[0].name, t.name)
        duration = t.duration / 1000
        tid = t.link.uri
        # set up filehandles, and get dummy size
        size = open_new_file(tid, duration)
        tracks[name] = (tid, size)
    playlist = {}
    playlist["tracks"] = tracks
    playlist["id"] = plid
    image = None
    if len(p.tracks):
        alb = p.tracks[0].album
        s = spotipy.Spotify()
        aob = s.album(alb.link.uri)
        images = aob["images"]
        if "LARGE" in images.keys():
            first = images["LARGE"]
        else:
            first = images[images.keys()[0]]
        r = requests.get(first["image_url"])
        print "url", first["image_url"]
        image = r.content
    if image:
        print "got image", len(image)
    else:
        print "no image"
    playlist["image"] = image
    print playlist["tracks"]
    return playlist


def get_playlists():
    print session.playlist_container
    playlists = session.playlist_container
    ret = {}
    for p in playlists:
        p = p.load()
        id = p.link.uri
        name = p.name
        # Don't add things that look like folders
        if not "/" in name:
            ret[name] = id
    return ret


def stop(track):
    session.player.unload()

def play(trackid):
    global current_track
    current_track = trackid
    # Play a track
    #TODO if playing, stop
    print "SPOTIFY SERVER, PLAYING"
    track = session.get_track(trackid).load()
    session.player.load(track)
    session.player.play()

def get(track, size, offset):
    # TODO: If we're at the end of the track, we need to
    # set a flag and return a sentinel, otherwise we'll
    # wait here forever if we think the file is longer than
    # it should be
    theio = spotify_ios[track]
    while True:
        d = theio.getvalue()
        print "got data len", len(d)
        print "want", offset, (size+offset)
        if len(d) >= size+offset:
            return d[offset:offset+size]
        # else wait for io to fill up more
        time.sleep(0.1)

if __name__ == "__main__":
    import sys
    playlists = get_playlists()
    print "got playlists"
    print playlists
    fs = spotifyfs.SFs(messages, response, trackqueue, playlists)
    fs.parse(errex=1)

    t = threading.Thread(None, fs.main)
    t.start()

    while True:
        try:
            m = messages.get(False)
            if m[0] == "stop":
                stop(m[1])
            elif m[0] == "play":
                play(m[1])
            elif m[0] == "get":
                data = get(m[1], m[2], m[3])
                response.put(data)
            elif m[0] == "playlist":
                data = load_playlist(m[1])
                trackqueue.put(data)
        except Queue.Empty:
            pass
        except KeyboardInterrupt:
            sys.exit(1)
        time.sleep(0.1)

# Wait for playback to complete or Ctrl+C
# try:
#     while not end_of_track.wait(0.1):
#         pass
#     print "track finished"
#     w.close()
# except KeyboardInterrupt:
#     pass

