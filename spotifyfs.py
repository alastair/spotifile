#!/usr/bin/env python

import fuse
import sys
import errno
import stat
import os
import time
import Queue

fuse.fuse_python_api = (0, 2)

hello_str = 'Hello World!\n'

class SFs(fuse.Fuse):
    def __init__(self, messagequeue, dataqueue, trackqueue, playlists, *args, **kw):
        self.messages = messagequeue
        self.data = dataqueue
        self.trackqueue = trackqueue
        # {name: uri}
        self.playlists = playlists
        # {playlisturi: {name: (uri, size)}
        self.files = {}
        # {playlisturi: imageurl}
        self.images = {}
        self.time = time.time()
        kw["version"] = fuse.__version__
        kw["usage"] = fuse.Fuse.fusage
        kw["dash_s_do"] = "setsingle"

        fuse.Fuse.__init__(self, *args, **kw)
        self.files = {"hello": hello_str}

    def getattr(self, path):
        st = fuse.Stat()
        st.st_uid = self.GetContext()["uid"]
        st.st_gid = self.GetContext()["gid"]
        st.st_atime = self.time
        st.st_mtime = self.time
        st.st_ctime = self.time
        print "trying to get attr for", path
        print path.count("/")
        print path.split("/")
        if path == '/':
            st.st_mode = stat.S_IFDIR | 0755
            st.st_nlink = 2
        elif path[1:] in self.files.keys():
            st.st_mode = stat.S_IFREG | 0444
            st.st_nlink = 1
            st.st_size = len(hello_str)
        elif path[1:].decode("utf-8") in self.playlists.keys():
            st.st_mode = stat.S_IFDIR | 0555
            st.st_nlink = 2
        elif path.count("/") == 2:
            parts = path.split("/")
            dname = parts[1].decode("utf-8")
            fname = parts[2]
            plid = self.playlists[dname]
            if fname == "folder.jpg":
                size = len(self.images[plid])
            else:
                filedata = self.files[plid][parts[2]]
                name, size = filedata
            st.st_mode = stat.S_IFREG | 0444
            st.st_nlink = 1
            st.st_size = size
        else:
            return -errno.ENOENT

        return st

    def readdir(self, path, offset):
        print "READDIR!"
        l = [".", ".."]
        if path == "/":
            l.extend([k.encode("utf-8") for k in self.playlists.keys()])
            l.extend(self.files.keys())
        else:
            # It's inside a playlist
            parts = path.split("/")
            dirname = parts[1].decode("utf-8")
            plid = self.playlists[dirname]
            print "in playlist", dirname, plid
            if plid in self.files:
                for f, v in self.files[plid].items():
                    l.append(f.encode("utf-8"))
            else:
                msg = ("playlist", plid)
                self.messages.put(msg)
                got = False
                while not got:
                    try:
                        stuff = self.trackqueue.get(False)
                        got = True
                        plid = stuff["id"]
                        image = stuff["image"]
                        tracks = stuff["tracks"]
                        self.files[plid] = tracks
                        self.images[plid] = image
                        if image:
                            self.files[plid]["folder.jpg"] = ("x", 1)
                        for f, v in self.files[plid].items():
                            l.append(f.encode("utf-8"))
                    except Queue.Empty:
                        time.sleep(0.1)
        for r in l:
            yield fuse.Direntry(r)

    def open(self, path, flags):
        # TODO: It's read-only, if flag is write, send
        # permission denied
        if path == "/hello":
            return 0
        elif path.count("/") == 2:
            parts = path.split("/")
            dname = parts[1].decode("utf-8")
            fname = parts[2].decode("utf-8")
            plid = self.playlists[dname]
            trid = self.files[plid][fname][0]
            if fname != "folder.jpg":
                msg = ("play", trid)
                print "playing", msg
                self.messages.put(msg)
            return 0
        return -errno.ENOENT

    def release(self, path, flags):
        if path == "/hello":
            return 0
        elif path.count("/") == 2:
            parts = path.split("/")
            dname = parts[1].decode("utf-8")
            fname = parts[2].decode("utf-8")
            plid = self.playlists[dname]
            trid = self.files[plid][fname][0]
            if fname != "folder.jpg":
                msg = ("stop", trid)
                self.messages.put(msg)
            return 0
        -errno.ENOENT

    def read(self, path, size, offset):
        if path == "/hello":
            return hello_str
        elif path.count("/") == 2:
            parts = path.split("/")
            dname = parts[1].decode("utf-8")
            fname = parts[2].decode("utf-8")
            plid = self.playlists[dname]
            stuff = -errno.ENOENT
            if fname == "folder.jpg":
                stuff = self.images[plid][offset:offset+size]
            else:
                trid = self.files[plid][fname][0]
                msg = ("get", trid, size, offset)
                self.messages.put(msg)
                got = False
                while not got:
                    try:
                        stuff = self.data.get()
                        got = True
                    except Queue.Empty:
                        pass
            return stuff
        return -errno.ENOENT

if __name__ == '__main__':
    fs = SFs(None, None, {}, version=fuse.__version__, usage=fuse.Fuse.fusage,
                    dash_s_do="setsingle")
    fs.parse(errex=1)
    fs.main()
