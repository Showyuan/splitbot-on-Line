# splitbot-on-Line

A LINE group-chat bot for splitting expenses. Members record who paid what with simple commands, and the bot computes the **minimum number of transfers** needed to settle up.

## Features

- Track expenses inside any LINE group chat with `/付`, `/代付`, `/欠`
- Auto-register every group member who has sent at least one message
- Resolve names by exact match, `@`-mention text, unique prefix, or the keyword `我` (the sender)
- Two-pointer settlement algorithm for the minimum number of transfers
- `/列表` shows expenses *and* the current settlement summary
- One active "event" per group; close it with `/結清` and start a new one
- `/help` renders as a LINE Flex Message card (column-aligned, configurable title)

## Commands

| Command | Example | Description |
|---|---|---|
| `/help` | `/help` | Show the Flex help card |
| `/新事件 <name>` | `/新事件 Okinawa trip` | Start a new event (one active event per group) |
| `/事件` | `/事件` | Show the current event |
| `/付 <amount> <payer> <others...>` | `/付 1200 我 A B` | Payer + others split equally |
| `/付 ... = <a> <b>...` | `/付 900 我 A B = 300 300 300` | Custom per-person amounts |
| `/代付 <amount> <others...>` | `/代付 500 A` | Sender pays, listed people owe; sender NOT included in the split |
| `/欠 <amount> <creditor>` | `/欠 800 A` | Sender owes the creditor (a plain IOU) |
| `/列表` | `/列表` | List all expenses plus settlement summary |
| `/刪 <id>` | `/刪 3` | Delete an expense |
| `/結算` | `/結算` | Show who pays whom |
| `/結清` | `/結清` | Close the current event |
| `/成員` | `/成員` | List registered members |

The keyword `all` / `全部` / `大家` / `全員` / `所有人` expands to every registered member of the group:

```
/付 1500 我 all       Sender pays 1500; all members split it equally
/代付 600 all         Sender pays 600 on behalf of everyone else (sender excluded)
```

Custom amounts (the `= ...` syntax) cannot be combined with `all`.

## Stack

- Python 3.11 + Flask
- [line-bot-sdk v3](https://github.com/line/line-bot-sdk-python)
- SQLite (single file, no daemon)
- gunicorn (production) behind nginx reverse proxy

Roughly 300 lines of Python — no ORM, no queue.

## Quick start (local development)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN

python -c "import db; db.init()"
python app.py
```

Flask listens on port `5050` by default. LINE webhooks require an HTTPS endpoint, so during development tunnel it with [ngrok](https://ngrok.com/):

```bash
ngrok http 5050
# Use the printed https://....ngrok.io/callback as the Webhook URL
```

### Optional branding

Set `BOT_TITLE` and `BOT_SUBTITLE` in `.env` to customize the `/help` Flex card header. Both default to English strings; see `.env.example`.

## LINE Developers Console setup

1. Create a Messaging API channel in the [LINE Developers Console](https://developers.line.biz/).
2. **Basic settings** tab → copy **Channel secret** into `.env` as `LINE_CHANNEL_SECRET`.
3. **Messaging API** tab:
   - **Channel access token** → click **Issue** → copy into `.env` as `LINE_CHANNEL_ACCESS_TOKEN`.
   - **Webhook URL** → set to `https://<your-host>/callback` (or `https://<your-host>/linebot/callback` if you mount the bot under a sub-path; see deploy below).
   - **Use webhook** → ON.
4. In the [LINE Official Account Manager](https://manager.line.biz/) → Settings → Response settings:
   - **Auto-response messages** → **OFF** (otherwise canned replies will shadow the bot's responses).
   - **Allow bot to join group chats** → **ON**.
5. Add the bot to a group: from LINE app, add the **Bot basic ID** (`@xxxx`) as a friend, then invite from the group.

## Production deploy (systemd + nginx)

Example templates live in `deploy/`:

- `deploy/systemd/splitbot.service` — systemd unit (uses `/opt/splitbot` as an example path; edit to match yours).
- `deploy/nginx/linebot.location.conf` — nginx `location` snippet that proxies `/linebot/` to `127.0.0.1:5050`.

Rough flow:

```bash
# 1. Place the project somewhere stable
sudo cp -r . /opt/splitbot
sudo useradd -r splitbot
sudo chown -R splitbot:splitbot /opt/splitbot

# 2. venv + dependencies
cd /opt/splitbot
sudo -u splitbot python3 -m venv venv
sudo -u splitbot ./venv/bin/pip install -r requirements.txt
sudo -u splitbot ./venv/bin/python -c "import db; db.init()"

# 3. nginx
sudo install -m 644 deploy/nginx/linebot.location.conf /etc/nginx/snippets/
# In your server { } block:
#   include /etc/nginx/snippets/linebot.location.conf;
sudo nginx -t && sudo systemctl reload nginx

# 4. systemd
sudo install -m 644 deploy/systemd/splitbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now splitbot

# 5. Logs
sudo journalctl -u splitbot -f
```

> **Paths with spaces** trip systemd's argument parser. If your project path contains a space, wrap `ExecStart`'s executable in double quotes.

## Data model

Four tables (see `schema.sql`):

- `members` — group members (`group_id` + `user_id` + `display_name`), populated automatically when anyone sends a message
- `events` — events per group; a partial unique index enforces at most one `active` event per group
- `expenses` — one expense row (payer, amount, optional note)
- `expense_shares` — each expense's debtors and per-person amounts

Settlement: sum each member's net balance over all expenses, then greedily pair the largest creditor with the largest debtor until everything zeros out. Not the NP-hard optimum, but produces a clean, predictable result for typical group sizes (3–10 people).

## Known limitations

- Group chats only — 1-on-1 messages are ignored.
- Members must send at least one message before they can be referenced in commands. The LINE API does not expose a group member list to bots, so registration must be observation-based.
- Display names containing whitespace get split by the tokenizer; the unique-prefix match (typing `Alex` instead of `Alex Wang`) covers the common case.
- Amounts are integers (no decimals).

## License

MIT — see `LICENSE`.
