# AITU TechShare — final Assignment 4 prototype

A student equipment rental/exchange website. **No sample products and no sample accounts** are included. Create your own student test account and add your own equipment. The website uses only Python standard-library modules; you do not need to install Flask, Django or SQL packages.

## How to start on Windows

1. Extract the entire ZIP into a normal folder (for example, Documents\AITU_TechShare). **Do not run directly from inside ZIP**.
2. Make sure Python 3.10 or later is installed. If `py` or `python` is not found, install Python first from python.org.
3. Double-click `run_windows.bat` and keep the black terminal window open.
4. The browser normally opens automatically. Otherwise copy the `Website:` address printed in the terminal. The terminal prints the exact `Database:` file path.
5. Click **Create account**, use a fictional test email ending in `@astanait.edu.kz` and create a password at least 8 characters long. There is **no pre-configured login**.
6. Log in, scroll to **Add your equipment**, fill out the form and click **Add equipment**. It will appear in the public catalog and in **My equipment**.
7. To test requests, register a second separate student test account, log into it in another browser profile/incognito session, open the item and submit a request. Back in the first account, open **Requests** to accept or decline.
8. Stop the server using `Ctrl+C` in the black terminal.

## Database: where are the records?

The real SQLite database lives at **database/techshare.db** (three tables: Users, Items, RentalRequests). Open it in **DB Browser for SQLite → Open Database → Browse Data → Items**, then refresh to see the item you added through the website. Do NOT open the .db file as text in VS Code. Do NOT open the same SQLite DB in two places for editing at the same time.

The public site never shows the Users table or every student's rental requests. **My equipment** and **Requests** are scoped to the currently logged-in user. Other students see only published catalog items. The database file is stored on the local server, not published at any website URL.

## Source layout

- `app.py` — site layout, routing, account sessions and form handlers.
- `database.py` — SQLite schema plus SQL SELECT/INSERT/UPDATE functions.
- `database/techshare.db` — real, initially empty SQLite file.
- `static/style.css` — site design, mobile layout and silent animation.
- `static/logo.svg`, `static/*.webp` — vector and optimised raster assets.
- `run_windows.bat`, `run_mac_linux.sh` — simple launch scripts.

## Assignment 4

The site includes real WebP images, SVG logo and a silent CSS animation. There is **no sound player**, no music, and no demo video embedded in the public website. The separate multimedia experiment files and the team demo-video storyboard are included in other deliverables. The real 2–3-minute narrated team recording, browser Network screenshots and actual post-recording export settings must be completed by students before submission.

## Important limits

This is an OFFLINE local academic prototype, not a live university service. Anyone can enter a test `@astanait.edu.kz` address; the website **does not verify control of that mailbox**. There is no production HTTPS, password-reset service, persistent session store, email delivery or payments. Never use real students' personal details or passwords. Explain these limitations honestly during defense.

## Saving your own data / old projects

After creating accounts and items, the `.db` file will contain your information. Always back up the whole project folder, or at least `database/techshare.db`, before replacing files. If you have an earlier website version with items you want to keep, turn off both servers, save backup copies, and only then carefully move the old `.db` into the new project's database folder. If table structures differ, manual migration may be required. Never overwrite a database containing work without a backup.
