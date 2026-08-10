## Project Features

- Automated certificate generation
- Upload student data using Excel
- Send certificates directly to students' emails
- Cloud-based certificate storage

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

## 2. Sending real emails (Gmail)

By default, emails are just printed to your terminal (safe for testing —
nothing actually gets sent). To send real emails through Gmail:

1. Turn on 2-Step Verification on the Gmail account you'll send from:
   https://myaccount.google.com/security
2. Create an **App Password**: https://myaccount.google.com/apppasswords
   (choose "Mail" as the app). Google gives you a 16-character password.
3. Set these environment variables before starting the server:

   ```bash
   export EMAIL_HOST_USER="youraddress@gmail.com"
   export EMAIL_HOST_PASSWORD="the16charapppassword"
   python manage.py runserver
   ```

   On Windows (PowerShell):
   ```powershell
   $env:EMAIL_HOST_USER="youraddress@gmail.com"
   $env:EMAIL_HOST_PASSWORD="the16charapppassword"
   python manage.py runserver
   ```

That's it — certificates will now be actually emailed. Gmail's free account
limits you to roughly 500 emails/day, which is plenty for a college event.

## 3. Excel sheet format

The first row must contain column headers with **"Name"** and
**"Email"** (or "Gmail") in them — case doesn't matter, and other columns
are ignored. If you're collecting sign-ups through a Google Form, open the
linked Google Sheet and go to **File → Download → Microsoft Excel (.xlsx)**,
then upload that file here.

| Name          | Email                     |
|---------------|----------------------------|
| Ananya Sharma | ananya@gmail.com           |
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

## 6. Deploying so it works from anywhere (not just your WiFi)

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
   - `EMAIL_HOST_USER` → your Gmail address
   - `EMAIL_HOST_PASSWORD` → your 16-character Gmail App Password
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
