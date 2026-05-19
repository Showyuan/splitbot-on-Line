from dataclasses import dataclass


class ParseError(Exception):
    pass


@dataclass
class PayCommand:
    amount: int
    payer_name: str
    participant_names: list[str]
    custom_shares: list[int] | None  # None = 均分


def parse_pay(args: str) -> PayCommand:
    """
    Parse args of `/付`:
      "1200 我 小明 小華"            → amount=1200, payer=我, participants=[我,小明,小華], custom=None
      "900 我 小明 小華 = 300 300 300" → custom_shares=[300,300,300]
    Payer is always the first name; payer is also a participant.
    """
    text = args.strip()
    if not text:
        raise ParseError("用法：/付 <金額> <付款人> [其他人...] [= <金額1> <金額2> ...]")

    left, eq, right = text.partition("=")
    left_tokens = left.split()
    if len(left_tokens) < 2:
        raise ParseError("用法：/付 <金額> <付款人> [其他人...]")

    try:
        amount = int(left_tokens[0])
    except ValueError:
        raise ParseError(f"金額必須是整數，收到「{left_tokens[0]}」")
    if amount <= 0:
        raise ParseError("金額必須大於 0")

    names = left_tokens[1:]
    # Dedupe while preserving order
    seen = set()
    participants = []
    for n in names:
        if n not in seen:
            seen.add(n)
            participants.append(n)

    payer = participants[0]

    custom_shares = None
    if eq:
        right_tokens = right.split()
        if len(right_tokens) != len(participants):
            raise ParseError(
                f"自訂金額數量({len(right_tokens)})必須等於人數({len(participants)})"
            )
        try:
            custom_shares = [int(t) for t in right_tokens]
        except ValueError:
            raise ParseError("自訂金額必須都是整數")
        if any(s < 0 for s in custom_shares):
            raise ParseError("自訂金額不可為負")
        if sum(custom_shares) != amount:
            raise ParseError(
                f"自訂金額總和 {sum(custom_shares)} 不等於 {amount}"
            )

    return PayCommand(
        amount=amount,
        payer_name=payer,
        participant_names=participants,
        custom_shares=custom_shares,
    )


def equal_split(amount: int, n: int) -> list[int]:
    """Split amount into n shares; remainder absorbed by first (= payer)."""
    base = amount // n
    remainder = amount - base * n
    return [base + remainder] + [base] * (n - 1)
