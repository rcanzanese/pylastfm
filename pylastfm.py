#!/usr/bin/env python

import requests
import hashlib
import os
import pickle
import time
import sys
import subprocess
import sqlite3
import argparse
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3

# You have to have your own unique two values for API_KEY and API_SECRET
# Obtain yours from http://www.last.fm/api/account for Last.fm
API_KEY = "INSERT API KEY HERE"
API_SECRET = "INSERT API SECRET HERE"
username = "INSERT USERNAME HERE"

# Where to find the banshee database
banshee_db_filename = "../.config/banshee-1/banshee.db"

def make_request(arguments, API_SECRET):
    """ Make an API request, returns JSON response as dict"""
    if API_SECRET:
        keys = arguments.keys()
        keys.sort()
        string = ""

        for key in keys:
            string += key
            string += arguments[key]

        string += API_SECRET
        sign = hashlib.md5(string)
        arguments['api_sig'] = sign.hexdigest()

    arguments["format"] = "json"
    response = requests.post("http://ws.audioscrobbler.com/2.0/?",
                             params=arguments)
    return response.json()


if __name__ == "__main__":

    # Get command line arguments
    parser = argparse.ArgumentParser(description='LastFM Player')
    parser.add_argument('artist', help='Artist for radio station')
    parser.add_argument('--genre', help='Genre to label MP3 file')
    args = parser.parse_args()

    artist = args.artist

    # Set default genre
    if args.genre:
        genre = args.genre
    else:
        genre = ""

    # Keep Track of downloaded songs in a pickle.
    try:
        with open('downloaded_songs.pickle', 'r') as f:
            database = pickle.load(f)
    except IOError:
        database = dict()

    result = make_request({'method': 'auth.getToken', 'api_key': API_KEY},
                          API_SECRET)
    token = result['token']

    # Make the user login via the web:
    print("You must login via your browser to approve this token for use:  ")
    url_test = "http://www.last.fm/api/auth?api_key=" + API_KEY + \
        "&token=" + token

    subprocess.call(["firefox", url_test])
    raw_input(url_test)

    # After authenticated, we need a session key
    result = make_request({'method': 'auth.getSession',
        'api_key': API_KEY, 'token': token}, API_SECRET)

    key = result['session']['key']

    # This is where we tune to similar artist radio station
    # for other URL formats see the API documentation
    result = make_request({'method': 'radio.tune', 'api_key': API_KEY,
        'sk': key, 'station': 'lastfm://artist/' + artist + '/similarartists'},
        API_SECRET)

    # The rest of this should loop forever!
    while True:

        # Get the playlist, which contains 5 songs
        result = make_request({'method': 'radio.getPlaylist',
            'api_key': API_KEY, 'sk': key, 'bitrate': '128'}, API_SECRET)

        tl = result['playlist']['trackList']['track']

        for track in tl:
            loc = track['location']
            title = track['title']
            identifier = track['identifier']
            album = track['album']
            creator = track['creator']
            duration = track['duration']
            image = track['image']

            # check whether song is already in the database
            if creator in database:
                if album + title + duration in database[creator]:
                    print("Skipping " + creator + " - " + title)
                    continue

            #Check whether song is in Banshee database
            conn = sqlite3.connect(banshee_db_filename)
            c = conn.cursor()
            query = "select CoreTracks.Title from CoreTracks " + \
                "INNER JOIN CoreArtists on " + \
                "(CoreArtists.ArtistID=CoreTracks.ArtistID) " + \
                "INNER JOIN CoreAlbums on " + \
                "(CoreAlbums.AlbumID=CoreTracks.AlbumID) AND " + \
                "CoreArtists.Name=\"" + creator + "\" AND " + \
                "CoreAlbums.Title=\"" + album + "\" AND " + \
                "CoreTracks.Title=\"" + title + "\""

            c.execute(query)
            r = c.fetchall()

            conn.close()

            if len(r) > 0:
                print("Skipping " + creator + " - " + title +
                    " --  Its already in Banshee!")
                continue

            print("Downloading " + creator + " - " + title)

            try:
                mw = requests.get(loc, timeout=60)
                art = requests.get(image, timeout=60)

                # Check whether folder exists
                directory = "./" + artist + "/" + creator + "/" + album + "/"
                if not os.path.exists(directory):
                    os.makedirs(directory)

                # Save the song
                with open(directory + title + '.mp3', 'w') as f:
                    f.write(mw.content)

                # Save the art
                with open(directory + 'coverart.jpg', 'w') as f:
                    f.write(art.content)
            except:
                print("Error: Could not open URL")
                continue

            if not mw:
                print("Error: Could not get URL")
                continue

            #ID3 tag it
            audiofile = MP3(directory + title + '.mp3', ID3=EasyID3)
            audiofile.add_tags(ID3=EasyID3)
            audiofile["title"] = title
            audiofile["artist"] = creator
            audiofile["album"] = album
            audiofile["genre"] = genre
            audiofile.save()

            # Add to database
            if creator in database:
                database[creator].append(album + title + duration)
            else:
                database[creator] = [album + title + duration]

            # Dump to pickle :
            with open('downloaded_songs.pickle', 'w') as f:
                pickle.dump(database, f)

        # Waiting in between
        WAIT = 15
        for i in range(WAIT):
            sys.stdout.write("Continuing in " + str(WAIT - i) + "...\r")
            sys.stdout.flush()
            time.sleep(1)
