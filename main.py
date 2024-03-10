from os.path import abspath, isfile
from os import remove, rename
import requests
from utils.audio import Audio
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH
from utils.metadata import Metadata
import subprocess
import argparse
from utils.token import AccessToken

parser = argparse.ArgumentParser(
                    prog='SpotifyDownloader',
                    description='Downloads Spotify songs')
parser.add_argument('--track_id', type=str, help='The track ID of the song')
parser.add_argument('--playlist_id', type=str, help='The playlist ID containing the songs')
parser.add_argument('--add-metadata', type=bool,
                    help='Add metadata to the song? (like artist, album, cover, etc)',
                    default=False, required=False)
args = parser.parse_args()

if __name__ == '__main__':
    if not isfile('spotify_dc.txt'):
        user_token = input('Please enter your Spotify "sp_dc" cookie: ')
        with open('spotify_dc.txt', 'w') as file:
            file.write(user_token.replace('Bearer ', ''))
    else:
        user_token = open('spotify_dc.txt', 'r').read()

    token = AccessToken()
    audio = Audio()
    metadata = Metadata()

    if args.track_id:
        # Download single track
        track_id = args.track_id

        try:
            track = audio.get_track(track_id)
        except requests.exceptions.HTTPError as e:
            token.refresh()
            track = audio.get_track(track_id)

        file_id = track['file'][4]['file_id']
        url = audio.get_audio_urls(file_id)[0]

        pssh = PSSH(requests.get(f'https://seektables.scdn.co/seektable/{file_id}.json').json()['pssh'])
        device = Device.load('device.wvd')
        cdm = Cdm.from_device(device)
        session_id = cdm.open()

        challenge = cdm.get_license_challenge(session_id, pssh)
        try:
            license = requests.post(audio.license_url, headers={
                'Authorization': f'Bearer {AccessToken().access_token}',
                'client-token': AccessToken().client_token,
                'Content-Type': 'application/octet-stream',
            }, data=challenge)
            license.raise_for_status()
        except requests.exceptions.HTTPError as e:
            token.get_client_token()
            license = requests.post(audio.license_url, headers={
                'Authorization': f'Bearer {AccessToken().access_token}',
                'client-token': AccessToken().client_token,
                'Content-Type': 'application/octet-stream',
            }, data=challenge)
            license.raise_for_status()

        cdm.parse_license(session_id, license.content)

        audio_response = requests.get(url)
        audio_file = abspath(f"./{track['name']}.mp3")
        audio_file_decrypted = abspath(f"./{track['name']}-decrypted.mp3")

        if isfile(audio_file):
            remove(audio_file)
        if isfile(audio_file_decrypted):
            remove(audio_file_decrypted)

        with open(audio_file, 'wb') as file:
            file.write(audio_response.content)

        for key in cdm.get_keys(session_id):
            subprocess.run([
                'ffmpeg', '-decryption_key', key.key.hex(), '-i', audio_file, audio_file_decrypted
            ])

        if args.add_metadata:
            metadata.set_metadata(track, audio_file_decrypted)

        remove(audio_file)
        rename(audio_file_decrypted, audio_file)

        cdm.close(session_id)

    elif args.playlist_id:
        # Download tracks from playlist
        playlist_id = args.playlist_id

        try:
            playlist_tracks = audio.get_playlist_tracks(playlist_id)
        except requests.exceptions.HTTPError as e:
            token.refresh()
            playlist_tracks = audio.get_playlist_tracks(playlist_id)

        for track in playlist_tracks:
            track_id = track['track']['id']

            try:
                track = audio.get_track(track_id)
            except requests.exceptions.HTTPError as e:
                token.refresh()
                track = audio.get_track(track_id)

            file_id = track['file'][4]['file_id']
            url = audio.get_audio_urls(file_id)[0]

            # Add the rest of the code for decryption and metadata as in the single track section

    else:
        print("Please provide either --track_id or --playlist_id argument.")
