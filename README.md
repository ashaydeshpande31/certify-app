# Certify

Certify puts every name on your certificate and emails it, or sends one message with a poster to everyone, straight from **your own Gmail**. Upload a list once (Excel, CSV, PDF or even a photo of the emails), click where the name goes, and press send. It is built for club and hackathon organizers.

**Why use it**

- **Your own Gmail, no shared inbox.** Mails go out from your account, so replies reach you. It is free, with no paid email service.
- **Made for hundreds of people.** It warns you before you hit Gmail's daily limit, sends big lists in rounds of 50 to stay out of spam, spots typos in emails, and lets you fix, edit, delete and re-add people.

---

## Run Certify on your own PC

You do this once, about 15 minutes. After that you start it with one command.

**Why you create your own Google keys:** Google only lets people sign in to an app that is still in "Testing" mode if they are added as test users, and the original author can't add everyone. So you make your own free Google project and add *yourself* as the test user. Nobody else's keys or permission are needed.

### What you need

- A computer with **Python 3.10 – 3.13** (3.12 is the safest). Get it from https://www.python.org/downloads/ and on Windows tick **"Add Python to PATH"** during install.
- **Git** (https://git-scm.com/downloads), or just use GitHub's green **Code → Download ZIP** button.
- A **Google account** (a normal @gmail.com works).

### Step 1. Get the code

```bash
git clone https://github.com/ashaydeshpande31/certify-app.git
cd certify-app
```

### Step 2. Install it

Windows (PowerShell or Command Prompt):

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Mac / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 3. Database (nothing to set up)

Certify uses a **SQLite file** (`db.sqlite3`) that it creates by itself in the project folder. You don't install or configure a database server.

```bash
python manage.py migrate
```

That builds all the tables. Your events and lists stay in that file on your PC. To start completely fresh, stop the server and delete `db.sqlite3`, then run `migrate` again.

*(Optional, for advanced users: to use PostgreSQL instead, set an environment variable `DATABASE_URL=postgres://USER:PASSWORD@HOST:5432/DBNAME` before running. Nothing else changes.)*

### Step 4. Google sign-in and Gmail (the one longer step)

1. Open https://console.cloud.google.com/ and sign in. At the top, click the project picker → **New project** → name it `certify` → **Create**. Make sure it is selected.
2. **Turn on the Gmail API:** menu → **APIs & Services → Library** → search **Gmail API** → **Enable**.
3. **Consent screen:** **APIs & Services → OAuth consent screen** (may be called **Google Auth platform**).
   - User type **External**, app name `Certify`, your email as support and developer contact. Save.
   - **Data access / Scopes → Add or remove scopes:** add `.../auth/userinfo.email`, `.../auth/userinfo.profile` and **`https://www.googleapis.com/auth/gmail.send`**. Save.
   - **Audience / Test users → Add users:** add **your own Gmail address** (the one you will send from). Save.
   - Leave the app in **Testing**. You do not need to publish it.
4. **Create the keys:** **APIs & Services → Credentials → Create credentials → OAuth client ID.**
   - Application type: **Web application**, name `Certify local`.
   - **Authorized redirect URIs → Add URI**, paste exactly:
     `http://127.0.0.1:8000/accounts/google/login/callback/`
   - **Create**. Copy the **Client ID** and **Client secret**.

### Step 5. Give Certify your keys

The keys stay on your PC. Never put them on GitHub.

**Windows:** in the `certify-app` folder, create a new file called `local_env.bat` with this inside (use your own values):

```bat
set GOOGLE_OAUTH_CLIENT_ID=paste-your-client-id.apps.googleusercontent.com
set GOOGLE_OAUTH_CLIENT_SECRET=paste-your-client-secret
```

`local_env.bat` is ignored by Git, so it will not be uploaded.

**Mac / Linux:** run these in the same terminal before starting (or put them in your shell profile):

```bash
export GOOGLE_OAUTH_CLIENT_ID="paste-your-client-id.apps.googleusercontent.com"
export GOOGLE_OAUTH_CLIENT_SECRET="paste-your-client-secret"
```

### Step 6. Start it

**Windows:** double-click **`start_certify.bat`** (it reads `local_env.bat`, updates the database and starts the server).

**Any system:**

```bash
python manage.py runserver
```

Open **http://127.0.0.1:8000/** in your browser and click **Sign in with Google**.

The first time, Google says **"Google hasn't verified this app"**. That is normal for your own test project. Click **Advanced → Go to Certify (unsafe)**, then tick the permission to **send email on your behalf** and continue. That permission (`gmail.send`) is how Certify mails from your account. It cannot read your inbox.

### Using it

1. **Send certificates:** upload your blank certificate design, upload the participant list (needs **Name** and **Email** columns), click where the name goes, check the preview, press send.
2. **Send updates:** write a subject and message, add the emails (file or typed), optionally add a poster, press send.
3. Watch the counter in the top bar. Gmail allows about **500 emails a day** on a normal account (2,000 on Google Workspace).

Next time, just start it again (`start_certify.bat`, or activate `venv` and run `python manage.py runserver`).

### If something goes wrong

| What you see | Fix |
|---|---|
| **Error 403: access_denied** or "app not verified / not allowed" | Your Gmail isn't a test user. Go back to Step 4.3 and add it under **Test users**. |
| **Error 400: redirect_uri_mismatch** | The redirect URI in Google must match exactly: `http://127.0.0.1:8000/accounts/google/login/callback/`. Open the site as `127.0.0.1:8000`, not `localhost:8000`. |
| Mails stop working after about a week | Apps in Testing mode lose their sign-in after **7 days**. Log out of Certify, then **Sign in with Google** again. |
| "Gmail refused" or "limit reached" | You sent about 500 in 24 hours. Wait and press send again. People not sent yet stay waiting. |
| `no such table` | Run `python manage.py migrate`. |
| `pip` or `python` not found | Reinstall Python and tick **Add Python to PATH**, then open a new terminal. |
| Port already in use | Use another port: `python manage.py runserver 8001`, and add the matching redirect URI (port 8001) in Google. |
| Page looks unstyled | Hard-refresh with **Ctrl + Shift + R**. |
