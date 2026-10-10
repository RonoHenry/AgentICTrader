"""Smoke test for the local MT5 terminal bridge.

Confirms the MetaTrader5 package can log into your account and read basic
account info, before agent/brokers/mt5.py gets wired into the full agent
graph. Credentials come from .env (see .env.example) — never hardcode them.

Run from the repo root:

    python test_mt5_connection.py
"""
from decouple import config

import MetaTrader5 as mt5


def main() -> None:
    login = config("MT5_LOGIN", cast=int)
    password = config("MT5_PASSWORD")
    server = config("MT5_SERVER")
    path = config("MT5_PATH", default="") or None

    print(f"Connecting to MT5 account {login} on {server}...")

    kwargs = {"login": login, "password": password, "server": server}
    if path:
        kwargs["path"] = path

    if not mt5.initialize(**kwargs):
        code, desc = mt5.last_error()
        print(f"FAILED to connect ({code}): {desc}")
        return

    account = mt5.account_info()
    if account is None:
        print("Connected, but could not read account info.")
    else:
        print("Connected.")
        print(f"  Login:    {account.login}")
        print(f"  Server:   {account.server}")
        print(f"  Balance:  {account.balance} {account.currency}")
        print(f"  Equity:   {account.equity} {account.currency}")
        print(f"  Leverage: 1:{account.leverage}")

    mt5.shutdown()


if __name__ == "__main__":
    main()
