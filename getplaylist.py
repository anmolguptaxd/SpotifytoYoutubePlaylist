from flask import Flask, request, redirect, session, url_for, render_template
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import uuid

app = Flask(__name__)

# Set the environment variables in code
os.environ['SPOTIPY_CLIENT_ID'] = '3ccee5fed52f4719957a790531670859'
os.environ['SPOTIPY_CLIENT_SECRET'] = '849030335b9b4f89b1f61820e6d1aaf5'
os.environ['SPOTIPY_REDIRECT_URI'] = 'http://127.0.0.1:5000/callback'

# Generate a random secret key - this should be kept secret in production
app.secret_key = str(uuid.uuid4())

# Configure your Spotify credentials
app.config['SPOTIPY_CLIENT_ID'] = '3ccee5fed52f4719957a790531670859'
app.config['SPOTIPY_CLIENT_SECRET'] = '849030335b9b4f89b1f61820e6d1aaf5'
app.config['SPOTIPY_REDIRECT_URI'] = 'http://127.0.0.1:5000/callback'
app.config['SCOPE'] = 'playlist-read-private'

# Helper function to get the current cache path
def session_cache_path():
    cache_directory = '.spotify_caches'
    if not os.path.isdir(cache_directory):
        os.makedirs(cache_directory)
    return os.path.join(cache_directory, session.get('uuid', ''))

@app.route('/')
def index():
    cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=session_cache_path())
    auth_manager = SpotifyOAuth(
        client_id=app.config['SPOTIPY_CLIENT_ID'],
        client_secret=app.config['SPOTIPY_CLIENT_SECRET'],
        redirect_uri=app.config['SPOTIPY_REDIRECT_URI'],
        scope=app.config['SCOPE'],
        cache_handler=cache_handler,
        show_dialog=True
    )

    if not session.get('uuid'):
        # Step 2. User is not logged in, generate a random session UUID
        session['uuid'] = str(uuid.uuid4())

    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        # Step 4. Display sign in link when no token
        auth_url = auth_manager.get_authorize_url()
        return render_template('index.html', auth_url=auth_url)

    # Step 5. Signed in, display playlists
    spotify = spotipy.Spotify(auth_manager=auth_manager)
    return export_playlists(spotify)

@app.route('/callback')
def callback():
    # Step 6. Being redirected from Spotify auth page with the code
    cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=session_cache_path())
    auth_manager = SpotifyOAuth(
        client_id=app.config['SPOTIPY_CLIENT_ID'],
        client_secret=app.config['SPOTIPY_CLIENT_SECRET'],
        redirect_uri=app.config['SPOTIPY_REDIRECT_URI'],
        scope=app.config['SCOPE'],
        cache_handler=cache_handler,
        show_dialog=True
    )
    # Exchange code for token
    auth_manager.get_access_token(request.args.get("code"))
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    # Remove the CACHE file so that a new user can authorize.
    try:
        os.remove(session_cache_path())
    except OSError as e:
        print(f"Error: {e.filename} - {e.strerror}.")
    session.clear()
    return redirect('/')

def export_playlists(spotify):
    # Fetch user playlists
    playlists = spotify.current_user_playlists()
    data = []

    for playlist in playlists['items']:
        if playlist['owner']['id'] == spotify.me()['id']:
            # Get all tracks in the playlist
            results = spotify.playlist_tracks(playlist['id'])
            tracks = results['items']
            while results['next']:
                results = spotify.next(results)
                tracks.extend(results['items'])
            
            # Format playlist data
            playlist_data = {
                'name': playlist['name'],
                'tracks': [f"{track['track']['name']} by {', '.join([artist['name'] for artist in track['track']['artists']])}" for track in tracks]
            }

            data.append(playlist_data)

    # You would typically render a template here
    return render_template('playlists.html', playlists=data)

if __name__ == '__main__':
    app.run(debug=True)
