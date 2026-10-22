# Smart Study News App — full-stack Gemini version

This is the Python-backed version of the Smart Study app. Flask serves the website and its Gemini API endpoint from one service. The Gemini key is read by `app.py` from a private local `.env` file or the server environment. It is never included in the browser code.

## Files

- `index.html` — page structure
- `styles.css` — page styling
- `app.js` — user interface and calls to the backend
- `app.py` — Flask website server and Gemini proxy
- `service-worker.js` and `manifest.webmanifest` — Android install and background push handling
- `generate_vapid.py` — creates the private/public keys used to send push notifications
- `requirements.txt` — Python packages
- `.env.example` — safe template for a local Gemini key
- `render.yaml` — Render deployment setup
- `.gitignore` — keeps the private `.env` and Python files out of commits

## Easiest way to run in VS Code

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/).
2. Open VS Code. Choose **File → Open Folder** and select this extracted project folder.
3. Create a Gemini API key at [Google AI Studio](https://aistudio.google.com/app/apikey).
4. In VS Code, choose **Terminal → New Terminal**. Install packages and create push keys:

   ```powershell
   python -m pip install -r requirements.txt
   python generate_vapid.py
   ```

   Copy the three lines printed by the key generator. Keep `VAPID_PRIVATE_KEY` private.
5. In VS Code's file list, copy `.env.example` and name the copy `.env`. Fill in your Gemini key and the three VAPID values. For `VAPID_SUBJECT`, replace `YOUR_EMAIL_ADDRESS` with your email address. Keep `.env` private; `.gitignore` prevents it from being committed.
6. Start the app:

   ```powershell
   python app.py
   ```

7. Leave the terminal open. Visit [http://localhost:3000/login](http://localhost:3000/login) in Chrome.
8. To stop the app, return to the terminal and press **Ctrl+C**.

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

## Enable Android notifications that arrive when the app is closed

Push notifications use the browser's push service and the Python server's scheduler. The app does not have to be open when the notification arrives.

1. In Render, add these environment variables from the generated keys: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, and `VAPID_SUBJECT`. Add `DATABASE_PATH` with value `/var/data/subscriptions.sqlite3`.
2. To keep the scheduler running and preserve subscriptions, upgrade the web service from Free to an always-on paid plan and attach a persistent disk mounted at `/var/data`. Render Free services sleep after 15 idle minutes and lose local files when they sleep or restart, so closed-app reminders cannot reliably work on the Free plan. Review Render's current pricing before upgrading.
3. Upload the updated project to GitHub and deploy the changes. Open the HTTPS Render link on the Android phone in Chrome.
4. In Chrome, open the site menu and choose **Install app** or **Add to Home screen**, then open Daylight from its new home-screen icon. Sign in.
5. In **Your study time**, select a time, switch on **Daily reminders**, and tap **Save my rhythm**. Allow notifications when Chrome asks. Check Android **Settings → Apps → Daylight/Chrome → Notifications** if alerts are muted.

The reminder uses your phone's local time zone. Push delivery depends on Android and Chrome allowing notifications and network delivery; battery saver or Do Not Disturb may delay or hide an alert. The reminder is sent once per local day. If the app server is stopped, asleep, or restarting at the reminder time, delivery may be delayed until it is available again.

The Blueprint starts on Render's Free web-service plan for safe initial setup. Free services sleep after 15 idle minutes and do not support persistent disks. Enable the always-on service and disk described above for closed-app push reminders. See [Render's free-service limits](https://render.com/docs/free) and [persistent disk setup](https://render.com/docs/disks).

## Demo account and scope

- Email: `sneha.minhas@mail.com`
- Password: `Study@123`

The sign-in is for a class demo, not secure account authentication. Preferences and progress live in each browser. The public AI endpoint has a small per-IP request limit. Do not enter personal or sensitive information.

The app uses `gemini-2.5-flash-lite`. Google's free-tier model eligibility and limits can change; check [Gemini pricing and terms](https://ai.google.dev/gemini-api/docs/pricing). The app sends the selected topic and recent study facts to Gemini.
