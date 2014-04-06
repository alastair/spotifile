Spotifile
---------

A fuse filesystem interface to your spotify playlists


To run
------

Add your username and password to `conf.py`. Register for a spotify API key
at https://devaccount.spotify.com/my-account/keys/ and download the binary
key file into this directory.

Python dependencies are in `requirements`

Run it like this:

    python spotifile.py -d -s <mountpoint>

Stop it by unmounting first:

    fusermount -u <mountpoint>

and then `^C` the process.

Issues
------

Currently the contents of a playlist is loaded on `readdir`. This means
that you must run `ls` on a directory before you can load a file from it.

The exact size of the file may be wrong (within about 44100 samples, based
on the duration of the file as reported by spotify). As a result, you may
get a deadlock at the end of the file because it doesn't check for the
end of the audio.

`^C` is not passed to the fuse thread so the script will stop when you quit
it. Make sure you run `fusermount -u` to unmount the fs too.

You need to specify some fuse options on the commandline (`-s` and `-d`),
which should probably be fixed

Audio data is sent via a callback in libspotify at about playback rate, so you
may get buffer underruns in your player occasionally. A fix to this would be to
return as much audio as is available in the buffer instead of waiting for it
to fill to the requested size

Seek doesn't work
