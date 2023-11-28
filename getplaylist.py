from flask import Flask, request, redirect, session, url_for, render_template
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os
import uuid
import google.auth
import requests
import os
from google.oauth2.credentials import Credentials
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()



app = Flask(__name__)

SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
YOUTUBE_CLIENT_SECRET = os.getenv('YOUTUBE_CLIENT_SECRET')
YOUTUBE_CLIENT_ID = os.getenv('YOUTUBE_CLIENT_ID')

# Configure your Spotify and YouTube credentials

SPOTIPY_REDIRECT_URI = 'https://spotifyto-youtube-playlist.vercel.app/callback'
YOUTUBE_CLIENT_SECRETS_FILE = "client-secret.json"
YOUTUBE_SCOPES = ['https://www.googleapis.com/auth/youtube']

app.secret_key = str(uuid.uuid4())

# The Spotify scope needed to read private playlists
SPOTIFY_SCOPE = 'playlist-read-private'

# The session cache path for the Spotify authentication token
def session_cache_path():
    cache_directory = '.spotify_caches'
    if not os.path.exists(cache_directory):
        os.makedirs(cache_directory)
    return os.path.join(cache_directory, session.get('uuid'))

# Helper function to create YouTube OAuth flow
def create_youtube_flow():
    flow = InstalledAppFlow.from_client_secrets_file(
        YOUTUBE_CLIENT_SECRETS_FILE, scopes=YOUTUBE_SCOPES)
    # This sets the redirect URI for the flow
    flow.redirect_uri = YOUTUBE_REDIRECT_URI
    return flow

# Helper function to get YouTube client
def get_youtube_client():
    creds_data = session.get('credentials')
    
    if not creds_data:
        return None
    
    # Construct credentials from the creds_data using the correct class method
    credentials = Credentials.from_authorized_user_info(creds_data)
    
    return build('youtube', 'v3', credentials=credentials)


@app.route('/')
def index():
    # Check if user has a session UUID, if not create one
    if not session.get('uuid'):
        session['uuid'] = str(uuid.uuid4())

    # Spotify OAuth2 flow
    cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=session_cache_path())
    auth_manager = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope=SPOTIFY_SCOPE,
        cache_handler=cache_handler,
        show_dialog=True
)

    # If there is no token in the cache for the user, redirect to Spotify Auth
    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        auth_url = auth_manager.get_authorize_url()
        return render_template('index.html', auth_url=auth_url)

    # If user is authenticated with Spotify but not with YouTube, redirect to YouTube Auth
    if 'credentials' not in session:
        return redirect(url_for('login_youtube'))

    # If user is authenticated with both, redirect to show playlists
    return redirect(url_for('show_playlists'))

@app.route('/callback')
def callback():
    cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=session_cache_path())
    auth_manager = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope=SPOTIFY_SCOPE,
        cache_handler=cache_handler,
        show_dialog=True
    )

    # Process the Spotify callback and redirect to YouTube login if needed
    auth_manager.get_access_token(request.args.get('code'))
    return redirect(url_for('login_youtube'))

@app.route('/login_youtube')
def login_youtube():
    flow = create_youtube_flow()
    # Generate a state token for CSRF protection
    state = str(uuid.uuid4())
    session['state'] = state
    authorization_url, state = flow.authorization_url(
        access_type='offline', 
        include_granted_scopes='true',
        state=state
    )
    return redirect(authorization_url)

YOUTUBE_REDIRECT_URI = 'https://spotifyto-youtube-playlist.vercel.app/youtube_callback'
@app.route('/youtube_callback')
def youtube_callback():
    # State validation should be implemented here
    state = session.get('state')
    if not state or state != request.args.get('state'):
        return "State does not match!", 400
    flow = create_youtube_flow()
    flow.fetch_token(authorization_response=request.url)

    if not flow.credentials:
        return "Failed to authenticate with YouTube", 400

    session['credentials'] = credentials_to_dict(flow.credentials)
    # Store the credentials in the session
    

    return redirect(url_for('show_playlists'))

def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes,
    }

@app.route('/show_playlists')
def show_playlists():
    # Get Spotify client
    cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=session_cache_path())
    spotify = spotipy.Spotify(auth_manager=SpotifyOAuth(cache_handler=cache_handler))
    
    # Fetch Spotify playlists
    spotify_playlists = spotify.current_user_playlists(limit=10)

    # Now, let's create YouTube playlists and add tracks
    youtube = get_youtube_client()
    if not youtube:
        return "Failed to get YouTube client", 400

    for sp_playlist in spotify_playlists['items']:
        # Create a new YouTube playlist with the same name as the Spotify playlist
        create_playlist_response = youtube.playlists().insert(
            part="snippet,status",
            body=dict(
                snippet=dict(
                    title=sp_playlist['name'],
                    description="Created from Spotify playlist"
                ),
                status=dict(
                    privacyStatus="private"
                )
            )
        ).execute()
        
        youtube_playlist_id = create_playlist_response['id']
        
        # Fetch tracks from the Spotify playlist
        sp_tracks = spotify.playlist_tracks(sp_playlist['id'])
        for track in sp_tracks['items']:
            track_name = track['track']['name']
            artist_name = track['track']['artists'][0]['name']
            
            # Search for the track on YouTube
            search_response = youtube.search().list(
                q=f"{artist_name} {track_name}",
                part="snippet",
                maxResults=1,
                type="video"
            ).execute()

            if search_response['items']:
                youtube_video_id = search_response['items'][0]['id']['videoId']
                
                # Add the video to the playlist
                youtube.playlistItems().insert(
                    part="snippet",
                    body=dict(
                        snippet=dict(
                            playlistId=youtube_playlist_id,
                            resourceId=dict(
                                kind="youtube#video",
                                videoId=youtube_video_id
                            )
                        )
                    )
                ).execute()

    # Return the list of Spotify playlists and a success message for YouTube operation
    return render_template('export_complete.html')

if __name__ == '__main__':
    app.run(debug=True)
