# app.py
import os
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# ---------------- Music Data ----------------
music_queue = []
now_playing = None

# ---------------- Routes ----------------
@app.route('/')
def home():
    return render_template('index.html', now_playing=now_playing, queue=music_queue)

@app.route('/play', methods=['POST'])
def play():
    global now_playing
    song = request.form.get('song')
    if song:
        music_queue.append(song)
        if not now_playing:
            now_playing = music_queue.pop(0)
    return redirect(url_for('home'))

@app.route('/next')
def next_song():
    global now_playing
    if music_queue:
        now_playing = music_queue.pop(0)
    else:
        now_playing = None
    return redirect(url_for('home'))

@app.route('/clear')
def clear_queue():
    global music_queue
    music_queue = []
    return redirect(url_for('home'))

# Optional: ignore bot-like requests (simple user-agent check)
@app.before_request
def allow_all_user_agents():
    # Render sometimes blocks requests if empty user-agent, allow all
    if 'User-Agent' not in request.headers:
        request.headers['User-Agent'] = 'Mozilla/5.0'

# ---------------- Run App ----------------
if __name__ == "__main__":
    # Use dynamic port for Render deployment
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
