import os

import db
import settle
from parser import parse_pay, equal_split, ParseError


BOT_TITLE = os.environ.get("BOT_TITLE", "LINE Split Bot")
BOT_SUBTITLE = os.environ.get("BOT_SUBTITLE", "Group expense splitter")


def _help_flex() -> dict:
    """Build a Flex Bubble for /book — column-aligned card."""
    cmd_rows = [
        ("/新事件", "建立新事件", "/新事件 沖繩旅遊"),
        ("/事件", "看當前事件", None),
        ("/付", "均分（含付款人）", "/付 1200 我 小明 小華"),
        ("/代付", "我付，他們攤", "/代付 500 小明"),
        ("/欠", "我欠他（IOU）", "/欠 800 小華"),
        ("/列表", "支出 + 結算摘要", None),
        ("/刪", "刪除某筆", "/刪 3"),
        ("/結算", "誰該轉給誰", None),
        ("/結清", "關閉當前事件", None),
        ("/成員", "列出已註冊成員", None),
        ("/加成員", "加匿名成員（不在群組裡的人）", "/加成員 小明"),
        ("/記得要帶", "加入提醒清單", "/記得要帶 雨傘"),
        ("/記得帶", "列出提醒清單", None),
        ("/記得帶刪", "刪除清單某項", "/記得帶刪 2"),
    ]

    def row(cmd: str, desc: str) -> dict:
        return {
            "type": "box", "layout": "horizontal", "spacing": "md",
            "contents": [
                {"type": "text", "text": cmd, "flex": 3, "weight": "bold",
                 "size": "sm", "color": "#FF8000"},
                {"type": "text", "text": desc, "flex": 5, "size": "sm",
                 "wrap": True, "color": "#333333"},
            ],
        }

    def example(text: str) -> dict:
        return {"type": "text", "text": text, "size": "xs",
                "color": "#555555", "wrap": True, "margin": "xs"}

    body_contents: list[dict] = [
        {"type": "text", "text": "指令", "weight": "bold",
         "size": "xs", "color": "#888888"},
        {"type": "separator", "margin": "xs"},
    ]
    for cmd, desc, _ex in cmd_rows:
        body_contents.append(row(cmd, desc))

    body_contents.append({"type": "separator", "margin": "lg"})
    body_contents.append(
        {"type": "text", "text": "範例", "weight": "bold",
         "size": "xs", "color": "#888888", "margin": "md"}
    )
    for _cmd, _desc, ex in cmd_rows:
        if ex:
            body_contents.append(example(ex))
    body_contents.append(example("/付 900 我 A B = 300 300 300  （自訂金額）"))
    body_contents.append(example("/付 1500 我 all  （所有人均分）"))

    body_contents.append({"type": "separator", "margin": "lg"})
    body_contents.append({
        "type": "text",
        "text": "「我」= 發訊息者；all / 全部 / 大家 = 所有成員",
        "size": "xxs", "color": "#888888", "wrap": True, "margin": "sm",
    })

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box", "layout": "vertical", "paddingAll": "12px",
            "backgroundColor": "#FF8000",
            "contents": [
                {"type": "text", "text": BOT_TITLE,
                 "weight": "bold", "size": "xl", "color": "#FFFFFF"},
                {"type": "text", "text": BOT_SUBTITLE,
                 "size": "xs", "color": "#FFF3E0", "margin": "xs"},
            ],
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": body_contents,
        },
    }


def cmd_help(*_args, **_kwargs) -> dict:
    return {"alt_text": BOT_TITLE, "contents": _help_flex()}


def cmd_new_event(group_id: str, args: str, **_) -> str:
    name = args.strip()
    if not name:
        return "用法：/新事件 <名稱>"
    if db.active_event(group_id):
        ev = db.active_event(group_id)
        return f"已有進行中的事件：「{ev['name']}」。請先 /結清 再開新事件。"
    db.create_event(group_id, name)
    return f"已建立事件「{name}」。開始用 /付 記帳吧。"


def cmd_event(group_id: str, **_) -> str:
    ev = db.active_event(group_id)
    if not ev:
        return "目前沒有進行中的事件。用 /新事件 <名稱> 建立。"
    return f"當前事件:「{ev['name']}」"


def cmd_close_event(group_id: str, **_) -> str:
    ev = db.active_event(group_id)
    if not ev:
        return "目前沒有進行中的事件。"
    db.close_event(ev["id"])
    return f"事件「{ev['name']}」已結清。"


def cmd_members(group_id: str, **_) -> str:
    members = db.list_members(group_id)
    if not members:
        return "還沒有成員註冊。請每個人在群組裡發一句話即可。"
    parts = []
    for m in members:
        if m["user_id"].startswith("anon:"):
            parts.append(f"{m['display_name']}（匿名）")
        else:
            parts.append(m["display_name"])
    return f"已註冊成員（{len(members)}）：{'、'.join(parts)}"


def cmd_add_member(group_id: str, args: str, **_) -> str:
    """/加成員 <name> — create an anonymous member (for people not in the LINE group)."""
    name = args.strip()
    if not name:
        return "用法：/加成員 <名字>　（例如：/加成員 小明）"
    if name in ("我", "self") or name in ALL_KEYWORDS:
        return f"「{name}」是保留字，請換一個名字。"
    if " " in name:
        return "名字不能含空白（會被指令解析拆開），請改用沒空白的暱稱。"
    if name.startswith("/") or name.startswith("@"):
        return "名字開頭不可用 / 或 @。"
    uid = db.add_anon_member(group_id, name)
    if uid is None:
        return f"「{name}」已經存在於群組成員裡了。"
    return (
        f"已加入匿名成員「{name}」。\n"
        f"現在可以在 /付、/代付、/欠、/結算 等指令中使用這個名字。"
    )


ALL_KEYWORDS = {"all", "All", "ALL", "全部", "全員", "大家", "所有人"}


def _resolve_name(group_id: str, name: str, sender_id: str, sender_name: str) -> str | None:
    """Map a name (incl. 「我」) to user_id; None if not found.

    Fallback order: literal 「我」 → exact display_name → unique case-insensitive prefix.
    """
    if name.startswith("@"):
        name = name[1:]
    if name in ("我", "self"):
        return sender_id
    uid = db.find_member_by_name(group_id, name)
    if uid:
        return uid
    needle = name.lower()
    matches = [
        m for m in db.list_members(group_id)
        if m["display_name"].lower().startswith(needle)
    ]
    if len(matches) == 1:
        return matches[0]["user_id"]
    return None


def _expand_all_keywords(names: list[str], group_id: str) -> list[str]:
    """Replace 'all' tokens with all registered display_names. Preserve order, dedup."""
    out: list[str] = []
    members_cache: list[str] | None = None
    for n in names:
        if n in ALL_KEYWORDS:
            if members_cache is None:
                members_cache = [m["display_name"] for m in db.list_members(group_id)]
            for m in members_cache:
                if m not in out:
                    out.append(m)
        elif n not in out:
            out.append(n)
    return out


def cmd_pay(group_id: str, args: str, sender_id: str, sender_name: str, **_) -> str:
    ev = db.active_event(group_id)
    if not ev:
        return "請先 /新事件 <名稱> 建立事件。"

    try:
        cmd = parse_pay(args)
    except ParseError as e:
        return str(e)

    if any(n in ALL_KEYWORDS for n in cmd.participant_names):
        if cmd.custom_shares is not None:
            return "用 all/全部 時不能搭配自訂金額（= ...）"
        if cmd.participant_names[0] in ALL_KEYWORDS:
            cmd.participant_names = ["我"] + cmd.participant_names
        cmd.participant_names = _expand_all_keywords(cmd.participant_names, group_id)

    user_ids: list[str] = []
    for name in cmd.participant_names:
        uid = _resolve_name(group_id, name, sender_id, sender_name)
        if uid is None:
            known = "、".join(m["display_name"] for m in db.list_members(group_id)) or "（無）"
            return (
                f"找不到成員「{name}」。\n"
                f"目前認得的名字：{known}\n"
                f"提醒：可用「我」代表你自己；含空白的名字可只打前幾字（如「Vicky」）"
            )
        if uid in user_ids:
            continue
        user_ids.append(uid)

    payer_id = user_ids[0]
    shares = cmd.custom_shares if cmd.custom_shares is not None \
        else equal_split(cmd.amount, len(user_ids))

    seq = db.add_expense(
        event_id=ev["id"],
        payer_id=payer_id,
        amount=cmd.amount,
        shares=list(zip(user_ids, shares)),
    )

    payer_name = db.display_name(group_id, payer_id)
    parts = []
    for uid, s in zip(user_ids, shares):
        parts.append(f"{db.display_name(group_id, uid)} {s}")
    return f"已記錄 #{seq}：{payer_name} 付 {cmd.amount}\n分擔：{'、'.join(parts)}"


def cmd_pay_for(group_id: str, args: str, sender_id: str, sender_name: str, **_) -> str:
    ev = db.active_event(group_id)
    if not ev:
        return "請先 /新事件 <名稱> 建立事件。"
    try:
        cmd = parse_pay(args)
    except ParseError as e:
        return f"用法：/代付 <金額> <為誰付> [其他人...] [= <金1> <金2>...]\n{e}"

    if any(n in ALL_KEYWORDS for n in cmd.participant_names):
        if cmd.custom_shares is not None:
            return "用 all/全部 時不能搭配自訂金額（= ...）"
        cmd.participant_names = _expand_all_keywords(cmd.participant_names, group_id)

    user_ids: list[str] = []
    for name in cmd.participant_names:
        uid = _resolve_name(group_id, name, sender_id, sender_name)
        if uid is None:
            known = "、".join(m["display_name"] for m in db.list_members(group_id)) or "（無）"
            return f"找不到成員「{name}」。\n目前認得：{known}"
        if uid == sender_id:
            continue
        if uid in user_ids:
            continue
        user_ids.append(uid)

    if not user_ids:
        return "沒有要分擔的人（用 /付 把自己也算進去？）"

    shares = cmd.custom_shares if cmd.custom_shares is not None \
        else equal_split(cmd.amount, len(user_ids))

    seq = db.add_expense(
        event_id=ev["id"],
        payer_id=sender_id,
        amount=cmd.amount,
        shares=list(zip(user_ids, shares)),
    )
    payer_name = db.display_name(group_id, sender_id)
    parts = [f"{db.display_name(group_id, uid)} {s}" for uid, s in zip(user_ids, shares)]
    return f"已記錄 #{seq}：{payer_name} 代付 {cmd.amount}\n分擔：{'、'.join(parts)}"


def cmd_owe(group_id: str, args: str, sender_id: str, sender_name: str, **_) -> str:
    ev = db.active_event(group_id)
    if not ev:
        return "請先 /新事件 <名稱> 建立事件。"
    toks = args.split()
    if len(toks) != 2:
        return "用法：/欠 <金額> <對誰>　（例如：/欠 500 葇）"
    try:
        amount = int(toks[0])
    except ValueError:
        return f"金額必須是整數，收到「{toks[0]}」"
    if amount <= 0:
        return "金額必須大於 0"
    creditor_id = _resolve_name(group_id, toks[1], sender_id, sender_name)
    if creditor_id is None:
        known = "、".join(m["display_name"] for m in db.list_members(group_id)) or "（無）"
        return f"找不到成員「{toks[1]}」。\n目前認得：{known}"
    if creditor_id == sender_id:
        return "不能欠自己 :)"

    seq = db.add_expense(
        event_id=ev["id"],
        payer_id=creditor_id,
        amount=amount,
        shares=[(sender_id, amount)],
    )
    return (
        f"已記錄 #{seq}："
        f"{db.display_name(group_id, sender_id)} 欠 {db.display_name(group_id, creditor_id)} {amount}"
    )


def cmd_list(group_id: str, **_) -> str:
    ev = db.active_event(group_id)
    if not ev:
        return "目前沒有進行中的事件。"
    exps = db.list_expenses(ev["id"])
    if not exps:
        return f"事件「{ev['name']}」目前沒有支出。"
    lines = [f"事件「{ev['name']}」支出："]
    for e in exps:
        payer = db.display_name(group_id, e["payer_id"])
        parts = "、".join(
            f"{db.display_name(group_id, uid)} {s}" for uid, s in e["shares"]
        )
        lines.append(f"#{e['seq']} {payer} 付 {e['amount']}（{parts}）")

    balances = settle.compute_balances(exps)
    transfers = settle.settle(balances)
    lines.append("")
    lines.append("目前結算：")
    if not transfers:
        lines.append("已平衡，不需轉帳")
    else:
        for from_id, to_id, amt in transfers:
            lines.append(
                f"{db.display_name(group_id, from_id)} → "
                f"{db.display_name(group_id, to_id)} NT${amt}"
            )
    return "\n".join(lines)


def cmd_delete(group_id: str, args: str, **_) -> str:
    ev = db.active_event(group_id)
    if not ev:
        return "目前沒有進行中的事件。"
    try:
        seq = int(args.strip())
    except ValueError:
        return "用法：/刪 <id>"
    ok = db.delete_expense(ev["id"], seq)
    return f"已刪除 #{seq}" if ok else f"找不到 #{seq}"


def cmd_settle(group_id: str, **_) -> str:
    ev = db.active_event(group_id)
    if not ev:
        return "目前沒有進行中的事件。"
    exps = db.list_expenses(ev["id"])
    if not exps:
        return f"事件「{ev['name']}」沒有任何支出。"
    balances = settle.compute_balances(exps)
    transfers = settle.settle(balances)
    if not transfers:
        return f"事件「{ev['name']}」已平衡，不需轉帳。"
    lines = [f"事件「{ev['name']}」結算："]
    for from_id, to_id, amt in transfers:
        from_name = db.display_name(group_id, from_id)
        to_name = db.display_name(group_id, to_id)
        lines.append(f"{from_name} → {to_name} NT${amt}")
    return "\n".join(lines)


def cmd_remind_add(group_id: str, args: str, **_) -> str:
    item = args.strip()
    if not item:
        return "用法：/記得要帶 <物品>　（例如：/記得要帶 雨傘）"
    seq = db.add_reminder(group_id, item)
    total = len(db.list_reminders(group_id))
    return f"已加入 #{seq}：{item}（清單共 {total} 項，用 /記得帶 查看）"


def cmd_remind_list(group_id: str, **_) -> str:
    items = db.list_reminders(group_id)
    if not items:
        return "提醒清單是空的。用 /記得要帶 <物品> 加入。"
    lines = ["記得帶："]
    for it in items:
        lines.append(f"#{it['seq']} {it['item']}")
    return "\n".join(lines)


def cmd_remind_del(group_id: str, args: str, **_) -> str:
    try:
        seq = int(args.strip())
    except ValueError:
        return "用法：/記得帶刪 <編號>　（例如：/記得帶刪 2）"
    ok = db.delete_reminder(group_id, seq)
    return f"已刪除 #{seq}" if ok else f"清單裡找不到 #{seq}"


COMMANDS = {
    "/book": cmd_help,
    "/help": cmd_help,  # alias
    "/新事件": cmd_new_event,
    "/事件": cmd_event,
    "/結清": cmd_close_event,
    "/成員": cmd_members,
    "/加成員": cmd_add_member,
    "/付": cmd_pay,
    "/代付": cmd_pay_for,
    "/欠": cmd_owe,
    "/列表": cmd_list,
    "/刪": cmd_delete,
    "/結算": cmd_settle,
    "/記得要帶": cmd_remind_add,
    "/記得帶": cmd_remind_list,
    "/記得帶刪": cmd_remind_del,
}


def dispatch(text: str, group_id: str, sender_id: str, sender_name: str):
    """Returns reply: str (text) | dict (flex with alt_text+contents) | None."""
    text = text.strip()
    if not text.startswith("/"):
        return None
    head, _, rest = text.partition(" ")
    handler = COMMANDS.get(head)
    if not handler:
        return f"未知指令「{head}」。輸入 /book 看可用指令。"
    return handler(
        group_id=group_id,
        args=rest,
        sender_id=sender_id,
        sender_name=sender_name,
    )
