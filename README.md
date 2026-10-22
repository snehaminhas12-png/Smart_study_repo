# Smart Study News App — full-stack Gemini version

This is the Python-backed version of the Smart Study app. Flask serves the website and its Gemini API endpoint from one service. The Gemini key is read by `app.py` from a private local `.env` file or the server environment. It is never included in the browser code.

## Files

- `index.html` — page structure
- `styles.css` — page styling
- `app.js` — user interface and calls to the backend
- `app.py` — Flask website server and Gemini proxy
- `requirements.txt` — Python packages
- `.env.example` — safe template for a local Gemini key
- `render.yaml` — Render deployment setup
- `.gitignore` — keeps the private `.env` and Python files out of commits

## Easiest way to run in VS Code

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/).
2. Open VS Code. Choose **File → Open Folder** and select this extracted project folder.
3. Create a Gemini API key at [Google AI Studio](https://aistudio.google.com/app/apikey).
4. In VS Code's file list, copy `.env.example` and name the copy `.env`. Open `.env` and replace `PASTE_YOUR_GEMINI_KEY_HERE` with your key. Keep `.env` private; `.gitignore` prevents it from being committed.
5. In VS Code, choose **Terminal → New Terminal**. Run these commands:

   ```powershell
   python -m pip install -r requirements.txt
   python app.py
   ```

6. Leave the terminal open. Visit [http://localhost:3000/login](http://localhost:3000/login) in Chrome.
7. To stop the app, return to the terminal and press **Ctrl+C**.

Python does not create a Gemini API key automatically. Create it once in AI Studio; the backend reads it from `.env`. If you leave the key as the example placeholder or omit `.env`, the site still opens and uses the sample facts. You do not need the VS Code Live Server extension for this app.

## Put the code on GitHub

1. Create a GitHub repository named `smart-study-gemini-app`.
2. Upload every file in this folder to the repository's top level. Do not upload `.env`; upload `.env.example` instead.
3. Commit the files. GitHub stores your code, but it does not run the Python backend.

## Publish the running app with Render

Render runs the Python server and serves the website. It gives the live app an `onrender.com` address.

1. Create or sign in to [Render](https://render.com/) using the GitHub account that owns your repository.
2. In Render, choose **New → Blueprint** and connect the `smart-study-gemini-app` repository.
3. Render reads `render.yaml` and asks for `GEMINI_API_KEY`. Paste your Google AI Studio key into that secret field, then apply the Blueprint.
4. Wait for the deployment to finish. Open the `onrender.com` address shown for your service.

The Blueprint uses Render's Free web-service plan. Free services sleep after 15 minutes without traffic, and the first request after sleep can take about a minute to start. Limits can change; see [Render's free-service details](https://render.com/docs/free).

## Demo account and scope

- Email: `sneha.minhas@mail.com`
- Password: `Study@123`

The sign-in is for a class demo, not secure account authentication. Preferences and progress live in each browser. The public AI endpoint has a small per-IP request limit. Do not enter personal or sensitive information.

The app uses `gemini-2.5-flash-lite`. Google's free-tier model eligibility and limits can change; check [Gemini pricing and terms](https://ai.google.dev/gemini-api/docs/pricing). The app sends the selected topic and recent study facts to Gemini.
