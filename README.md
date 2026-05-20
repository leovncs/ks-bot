# Kingshot Bot | Kingdom 125

A Discord bot that automates the kvk preparation schedule for kingdom alliances.
Members submit a screenshot of their speedup inventory alongside their availability,
and the bot allocates everyone to a 30-minute slot across the three event days,
prioritising players with the highest relevant speedup totals.

---

## Features

- **Screenshot OCR** — reads speedup values directly from in-game screenshots
  (supports Day / Hour / Minute display modes; handles thousands separators)
- **Natural-language availability parsing** — members can describe their availability
  however feels natural; the bot extracts the days and time windows automatically
- **Automatic slot allocation** — players with more relevant speedups are allocated
  first; everyone else fills remaining slots within their preferred window
- **Announcements integration** — publish the schedule to a dedicated channel with
  one command; members look up their personal slot with `!myschedule`
- **Controlled visibility** — the `#my-schedule` channel is hidden until the
  schedule is published, and hidden again when submissions close

---

## Slot structure

Slots are **30 minutes wide**, always at `:15` and `:45`.

| Index | Slot  | Meaning |
|-------|-------|---------|
| 0     | 23:45 | Pre-reset (the evening before the event day begins) |
| 1     | 00:15 | First regular slot of the event day |
| …     | …     | … |
| 48    | 23:45 | Last slot of the event day |

The **23:45 slot on Day 1** is shared with Day 2 — it covers the last 15 min of
Day 1 and the first 15 min of Day 2.  Day 4 follows the same pattern as Day 1.

---

## Setup

### 1. Install Tesseract OCR

**Ubuntu / Debian**
```bash
sudo apt-get install -y tesseract-ocr
```

**macOS**
```bash
brew install tesseract
```

**Windows**
Download the installer from <https://github.com/UB-Mannheim/tesseract/wiki>.
After installing, either add `Tesseract-OCR` to your system `PATH`, or set
`TESSERACT_PATH` in your `.env` file (see below).

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Create your `.env` file

```bash
cp .env.example .env
```

Edit `.env` and fill in your `DISCORD_TOKEN`.
If Tesseract is not on your `PATH` (Windows), also set `TESSERACT_PATH`.

### 4. Enable Discord intents

In the [Discord Developer Portal](https://discord.com/developers/applications),
go to your bot → **Bot** tab and enable:

- **Server Members Intent**
- **Message Content Intent**

### 5. Run the bot

```bash
python bot.py
```

---

## First-time configuration

Run each command **inside the channel you want to designate**:

| Command | Channel | Description |
|---------|---------|-------------|
| `!setup submissions` | `#submissions` | Where members send their signup |
| `!setup admin` | `#bot-admin` | Where admins run commands |
| `!setup announcements` | `#announcements` | Where the schedule is published |
| `!setup lookup` | `#my-schedule` | Where members check their slot (auto-hidden) |

Check current config at any time: `!setup status`

---

## Command reference

### Member commands

| Command | Channel | Description |
|---------|---------|-------------|
| _(send message with screenshot)_ | `#submissions` | Submit speedups + availability |
| `!myschedule` | `#my-schedule` | View your allocated slot(s) |

**Submission examples** (mention the bot and describe your availability):
```
@Bot Day 1: 10:00-16:00  Day 2: any time  Day 4: 21:00-23:00
@Bot Sign me up any time close to reset on all 3 days
@Bot Day 1 and Day 4 between 20:00 and 22:00
@Bot available day 2 from 14:00 to 18:00
```

---

### Admin commands

All admin commands work in the `#bot-admin` channel (or for server administrators anywhere).

#### Submissions

| Command | Description |
|---------|-------------|
| `!submissions open` | Re-open #submissions |
| `!submissions close` | Close #submissions and hide #my-schedule |

#### Schedule

| Command | Description |
|---------|-------------|
| `!schedule generate` | Build the schedule from all submissions |
| `!schedule preview` | Preview all days in the admin channel |
| `!schedule preview day1` | Preview a single day (`day1` / `day2` / `day4`) |
| `!schedule publish` | Post all days to #announcements + open #my-schedule |
| `!schedule publish day1` | Publish a single day |
| `!schedule clear` | Wipe the generated schedule (keeps submissions) |

#### Users

| Command | Description |
|---------|-------------|
| `!users list` | List all registered members with speedups and availability |
| `!users remove @member` | Remove a member's submission |

#### Other

| Command | Description |
|---------|-------------|
| `!status` | Show bot state (channels, submission count, schedule) |
| `!reset CONFIRM` | ⚠️ Wipe all data and reset the bot |

---

## Event flow

```
1.  Members submit in #submissions
        ↓
2.  !submissions close          ← closes registrations
        ↓
3.  !schedule generate          ← builds the allocation
        ↓
4.  !schedule preview           ← admins review before publishing
        ↓
5.  !schedule publish           ← posts to #announcements, opens #my-schedule
        ↓
6.  Members use !myschedule     ← each member sees their personal slot
```

---

## Discord permissions required

The bot needs the following permissions on the server:

- Read Messages / View Channels
- Send Messages
- Embed Links
- Read Message History
- Manage Messages *(to delete `!myschedule` commands in #my-schedule)*
- Manage Channels *(to show/hide #my-schedule)*

---

## Project structure

```
kingshot_bot/
├── bot.py          Entry point
├── config.py       Shared constants (day labels, slot lists, colors)
├── database.py     JSON state persistence
├── ocr.py          Screenshot reading via Tesseract
├── parser.py       Availability message parsing
├── scheduler.py    Slot allocation algorithm
├── cogs/
│   ├── setup.py        !setup commands (first-time config)
│   ├── submissions.py  Member signup listener
│   ├── admin.py        Schedule generation and publishing
│   └── lookup.py       !myschedule for members
├── data/           Runtime state (git-ignored)
├── .env            Secrets (git-ignored)
├── .env.example    Template for .env
├── .gitignore
├── requirements.txt
└── README.md
```