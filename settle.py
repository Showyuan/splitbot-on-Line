from collections import defaultdict


def compute_balances(expenses: list[dict]) -> dict[str, int]:
    """
    Returns {user_id: net_amount}.
    Positive = others owe them. Negative = they owe others.
    """
    balance: dict[str, int] = defaultdict(int)
    for e in expenses:
        balance[e["payer_id"]] += e["amount"]
        for uid, share in e["shares"]:
            balance[uid] -= share
    return dict(balance)


def settle(balances: dict[str, int]) -> list[tuple[str, str, int]]:
    """
    Two-pointer settlement.
    Returns list of (from_user_id, to_user_id, amount).
    """
    creditors = sorted(
        [(uid, amt) for uid, amt in balances.items() if amt > 0],
        key=lambda x: -x[1],
    )
    debtors = sorted(
        [(uid, -amt) for uid, amt in balances.items() if amt < 0],
        key=lambda x: -x[1],
    )

    transfers: list[tuple[str, str, int]] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debtor_id, debt = debtors[i]
        creditor_id, credit = creditors[j]
        pay = min(debt, credit)
        if pay > 0:
            transfers.append((debtor_id, creditor_id, pay))
        debt -= pay
        credit -= pay
        debtors[i] = (debtor_id, debt)
        creditors[j] = (creditor_id, credit)
        if debt == 0:
            i += 1
        if credit == 0:
            j += 1
    return transfers
