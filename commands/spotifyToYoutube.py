from collections import deque
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import urllib.request
import bs4
import urllib
import ytmusicapi


def getTracks(playlistURL):
    # Creating and authenticating our Spotify app.

    client_credentials_manager = SpotifyClientCredentials(
        "e0aeec28e650456284327850633f8cc0", "1e8cedc2abf043088aa5ca255f27ac68")
    spotify = spotipy.Spotify(
        client_credentials_manager=client_credentials_manager)

    # Getting a playlist.
    results = spotify.playlist_items(
        playlist_id=playlistURL,
        additional_types=(
            'track',
        ))

    trackList = []
    # For each track in the playlist.
    for i in results["items"]:
        # In case there's only one artist.
        if i["track"]["artists"].__len__() == 1:
            # We add trackName - artist.
            trackList.append(
                i["track"]["name"] +
                " - " +
                i["track"]["artists"][0]["name"])
        # In case there's more than one artist.
        else:
            nameString = ""
            # For each artist in the track.
            for index, b in enumerate(i["track"]["artists"]):
                nameString += (b["name"])
                # If it isn't the last artist.
                if i["track"]["artists"].__len__() - 1 != index:
                    nameString += ", "
            # Adding the track to the list.
            trackList.append(i["track"]["name"] + " - " + nameString)

    return trackList


def getSingleTrack(songURL):
    client_credentials_manager = SpotifyClientCredentials(
        "e0aeec28e650456284327850633f8cc0", "1e8cedc2abf043088aa5ca255f27ac68")
    spotify = spotipy.Spotify(
        client_credentials_manager=client_credentials_manager)
    result = spotify.track(songURL)
    if result["artists"].__len__() == 1:
        # We add trackName - artist.
        return searchYoutube(
            result["name"] +
            " - " +
            result["artists"][0]["name"])
    # In case there's more than one artist.
    else:
        nameString = ""
        # For each artist in the track.
        for index, b in enumerate(result["artists"]):
            nameString += (b["name"])
            # If it isn't the last artist.
            if result["artists"].__len__() - 1 != index:
                nameString += ", "
        # Adding the track to the list.
        return searchYoutube(result["name"] + " - " + nameString)


yt = ytmusicapi.YTMusic(auth="commands/config.json")


def searchYoutube(songName):
    video = yt.search(query=songName, limit=1, filter='videos')
    return "https://www.youtube.com/watch?v=" + video[0]["videoId"]


def getSongs(url):
    song = ""
    songs = deque()
    tracks = getTracks(url)
    index = 0
    for i in tracks:
        if index == 0:
            song = searchYoutube(i)
        songs.append(searchYoutube(i))
        index += 1
    return song, songs
