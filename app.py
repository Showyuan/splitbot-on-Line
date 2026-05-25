import os
import logging

from dotenv import load_dotenv
from flask import Flask, abort, request

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    GroupSource,
)

import db
import commands

load_dotenv()

CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
PORT = int(os.environ.get("PORT", 5000))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("splitbot")

app = Flask(__name__)
handler = WebhookHandler(CHANNEL_SECRET)
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)

# Ensure schema + migrations are applied on startup (also under gunicorn,
# where __main__ does not run). Idempotent.
db.init()


@app.route("/", methods=["GET"])
def index():
    return "splitbot ok", 200


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event: MessageEvent):
    source = event.source
    if not isinstance(source, GroupSource):
        # Only support group chats for now
        _reply(event.reply_token, "目前只支援群組使用。請把 bot 加進群組。")
        return

    group_id = source.group_id
    user_id = source.user_id
    text = event.message.text

    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        # Auto-register sender: fetch their display name
        sender_name = user_id[:6]
        try:
            profile = messaging_api.get_group_member_profile(group_id, user_id)
            sender_name = profile.display_name
            db.upsert_member(group_id, user_id, sender_name)
        except Exception as e:
            log.warning("get_group_member_profile failed: %s", e)

        reply = commands.dispatch(
            text=text,
            group_id=group_id,
            sender_id=user_id,
            sender_name=sender_name,
        )
        if reply is None:
            return  # not a command, stay silent
        _reply_via(messaging_api, event.reply_token, reply)


def _reply(reply_token: str, payload):
    with ApiClient(configuration) as api_client:
        _reply_via(MessagingApi(api_client), reply_token, payload)


def _reply_via(messaging_api: MessagingApi, reply_token: str, payload):
    """payload: str (text) or dict with 'alt_text' + 'contents' (Flex)."""
    if isinstance(payload, dict) and "contents" in payload:
        msg = FlexMessage(
            alt_text=payload.get("alt_text", "分帳 Bot"),
            contents=FlexContainer.from_dict(payload["contents"]),
        )
    else:
        msg = TextMessage(text=str(payload))
    messaging_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[msg],
        )
    )


if __name__ == "__main__":
    db.init()
    app.run(host="0.0.0.0", port=PORT)
