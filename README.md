# Certify — Automated Certificate Generator & Mailer

Upload a student list (Excel) and a certificate template once. Certify places
each student's name on the certificate automatically, turns it into a PDF,
and emails it directly to their Gmail — ready for them to download and post
on LinkedIn.

Built with Django + Pillow (image/PDF generation) + openpyxl (Excel parsing).

## Features

- Upload a blank certificate design (PNG/JPG) and an Excel sheet (from a
  Google Form response sheet, or any spreadsheet with Name + Email columns).
- Click-to-position tool: click on your certificate to mark exactly where
  student names go, live preview, choose font/size/color/alignment.
- One click generates a personalized PDF for every student and emails it.
- Per-student status tracking (pending / generated / sent / failed) with
  resend for individual students.
- Public certificate verification page (`/verify/<id>/`) — a unique link
  included in every email so anyone (e.g. a LinkedIn viewer or recruiter)
  can confirm the certificate is genuine.
- **Google Sign-In** — every organizer signs in with their own Google
  account; their events are private to them, and certificates are emailed
  from their own Gmail via the Gmail API (see §2).
- **Personal message per event** — write a short note (e.g. "Thanks for
  attending!") when creating an event, or edit it anytime from the
  student-list page; it's included in every certificate email for that
  event.
- **Delete event** — remove an event (and all its certificates) you no
  longer need, right from the events grid.
- Clean, distinctive "official document" themed UI — not a bootstrap default.

## 1. Setup

```bash
cd certify_project
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser   # optional, for /admin/
python manage.py runserver
```

Open **http://127.0.0.1:8000/**.

## 2. Google Sign-In (each organizer sends from their own Gmail)

Certify now uses **Google Sign-In**. Anyone you share the app with signs in
with their own Google account, and certificates are emailed straight from
*their* Gmail — not a shared inbox. Events are private to whoever created
them.

### 2a. Create a Google OAuth client (one-time, for you as the app owner)

1. Go to https://console.cloud.google.com/ and select (or create) the
   `certify-app` project you already set up.
2. **APIs & Services → OAuth consent screen** — set it to "External", add
   your app name/logo, and add the scope
   `https://www.googleapis.com/auth/gmail.send`. While the app is in
   "Testing" mode, add every Google account that should be able to sign in
   (yourself + teammates) under **Test users** — Google blocks anyone else
   until you publish the app.
3. **APIs & Services → Library** — enable the **Gmail API**.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   → Application type **Web application**. Under **Authorized redirect
   URIs**, add every URL you'll run this from, each ending in
   `/accounts/google/login/callback/`, e.g.:
   - `http://127.0.0.1:8000/accounts/google/login/callback/` (local)
   - `https://your-ngrok-subdomain.ngrok-free.app/accounts/google/login/callback/` (ngrok — see §6)
   - `https://your-app.onrender.com/accounts/google/login/callback/` (Render)
5. Copy the **Client ID** and **Client secret** it gives you.

### 2b. Tell Certify about the client

Set two environment variables before running the server:

```bash
export GOOGLE_OAUTH_CLIENT_ID="xxxx.apps.googleusercontent.com"
export GOOGLE_OAUTH_CLIENT_SECRET="xxxx"
```

On Windows (PowerShell):
```powershell
$env:GOOGLE_OAUTH_CLIENT_ID="xxxx.apps.googleusercontent.com"
$env:GOOGLE_OAUTH_CLIENT_SECRET="xxxx"
```

Then run migrations (new fields were added) and start the server:

```bash
python manage.py migrate
python manage.py runserver
```

Click **"Sign in with Google"** in the top bar. The first time, Google will
show a consent screen asking to let Certify "send email on your behalf" —
that's the `gmail.send` permission, needed so certificates go out from that
user's own address. Approve it once; Certify securely stores the token so
future sends don't ask again.

**Fallback:** if `GOOGLE_OAUTH_CLIENT_ID`/`SECRET` aren't set, or a signed-in
user hasn't granted Gmail access yet, Certify automatically falls back to
sending via the shared `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` SMTP
account (see below), so the app still works without Google Sign-In
configured.

### 2c. (Optional) shared fallback Gmail account via App Password

1. Turn on 2-Step Verification on the Gmail account you'll send from:
   https://myaccount.google.com/security
2. Create an **App Password**: https://myaccount.google.com/apppasswords
   (choose "Mail" as the app). Google gives you a 16-character password.
3. Set these environment variables:

   ```bash
   export EMAIL_HOST_USER="youraddress@gmail.com"
   export EMAIL_HOST_PASSWORD="the16charapppassword"
   ```

Gmail's free account limits you to roughly 500 emails/day, which is plenty
for a college event.

## 3. Excel sheet format

The first row must contain column headers with **"Name"** and
**"Email"** (or "Gmail") in them — case doesn't matter, and other columns
are ignored. If you're collecting sign-ups through a Google Form, open the
linked Google Sheet and go to **File → Download → Microsoft Excel (.xlsx)**,
then upload that file here.

| Name          | Email                     |
|---------------|----------------------------|
| Ashay Deshpande | ashaydeshpande@gmail.com           |
| Rohit Verma   | rohit@gmail.com            |

## 4. Certificate template

Upload the certificate design as a PNG or JPG **without any name already on
it** — just the blank layout, borders, logos, signatures, etc. After
uploading, you'll click directly on the image to mark where the student's
name should appear, and choose the font/size/color live.

## 5. Project structure

```
certify_project/
├── certificates/            # the main app
│   ├── models.py            # Event, Student
│   ├── views.py             # upload, position tool, generate/send
│   ├── utils.py             # excel parsing, PDF generation, email sending
│   ├── forms.py
│   ├── templates/certificates/
│   └── static/certificates/css/style.css
├── certify_project/
│   ├── settings.py          # email config reads from env vars
│   └── urls.py
├── manage.py
└── requirements.txt
```

## 6. Quick sharing with ngrok (no deploy needed)

If you just need to demo the app or let a few people use it *while your
laptop stays on*, ngrok tunnels your local server to a public HTTPS URL in
seconds — no hosting account needed.

1. Install ngrok: https://ngrok.com/download, then `ngrok config add-authtoken <your-token>`
   (free account, token is on your ngrok dashboard).
2. In one terminal, run Certify as usual:
   ```bash
   python manage.py runserver
   ```
3. In a second terminal:
   ```bash
   ngrok http 8000
   ```
   ngrok prints a **Forwarding** URL like `https://a1b2c3d4.ngrok-free.app`.
4. Add that exact URL to Django and Google so cookies/CSRF and OAuth work
   over the tunnel:
   ```bash
   export ALLOWED_HOSTS="a1b2c3d4.ngrok-free.app,127.0.0.1"
   export CSRF_TRUSTED_ORIGINS="https://a1b2c3d4.ngrok-free.app"
   export SITE_URL="https://a1b2c3d4.ngrok-free.app"
   ```
   (On Windows PowerShell, use `$env:NAME="value"` for each.)
5. Add `https://a1b2c3d4.ngrok-free.app/accounts/google/login/callback/` to
   **Authorized redirect URIs** on your Google OAuth client (§2a, step 4),
   and add your testers' Gmail addresses under **Test users** on the OAuth
   consent screen if the app is still in "Testing" mode.
6. Restart `runserver` after setting the env vars, then share the ngrok URL.

**Note:** ngrok's free plan gives you a new random URL every time you
restart it, so you'd need to re-add the new callback URL to Google each
time. A [paid ngrok plan](https://ngrok.com/pricing) or a reserved free
domain (`ngrok http --domain=your-static-domain.ngrok-free.app 8000`) keeps
the URL fixed. For anything longer-lived than a demo, Render (§7 below) is
usually less hassle since the URL never changes.

## 7. Deploying so it works from anywhere (not just your WiFi)

This project is ready to deploy to **Render** for free — no credit card
needed. This gives you a real public URL (e.g. `https://certify-xyz.onrender.com`)
that works from any phone, laptop, or network, and keeps running even when
your own laptop is off.

1. **Push this project to GitHub** (create a new repo, upload this folder).

2. Go to https://render.com → sign up (GitHub login is easiest) →
   **New +** → **Web Service** → connect your GitHub repo.

3. Render will detect the included `render.yaml` and pre-fill everything
   (build command, start command). Just confirm.

4. Before the first deploy, add these **Environment Variables** in Render's
   dashboard (Settings → Environment):
   - `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` → from §2a
     (and add `https://<your-render-url>/accounts/google/login/callback/`
     to that OAuth client's Authorized redirect URIs)
   - `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` → optional shared-account
     fallback (§2c) for users who haven't signed in with Google
   (Render already generates `SECRET_KEY` and sets `DEBUG=False` for you
   via `render.yaml`.)

5. Click **Deploy**. First deploy takes a few minutes. Once it's live,
   Render gives you a URL like `https://certify-xyz.onrender.com` —
   that's your app, reachable from anywhere.

**One important limitation on Render's free tier:** the filesystem is
*ephemeral* — meaning uploaded templates and generated certificate PDFs
get wiped whenever the service restarts or redeploys (free services also
"sleep" after 15 minutes of no traffic and wake up on the next visit,
which takes ~30-60 seconds). This is fine for a hackathon demo/judging
session, but **don't rely on it as permanent storage** for certificates
after the event — download important certificates or ask me to wire up
free cloud storage (e.g. Cloudinary) if you need files to persist
long-term.

## Notes for your submission

- Certificate generation uses Pillow to draw text onto your template image,
  then saves it directly as a PDF — no external services needed.
- Emails are sent with Django's built-in `EmailMessage`, attaching the
  generated PDF.
- Each student gets a unique certificate ID (UUID) and a verification page,
  which is a nice extra to mention in your hackathon pitch/report.
