"""The directory reading carries the real account state (AD userAccountControl, bit 2 = disabled)."""
from app.actions.directory_snapshot import _account_enabled


def test_account_state_from_user_account_control() -> None:
    assert _account_enabled("512") is True  # NORMAL_ACCOUNT
    assert _account_enabled(514) is False  # NORMAL_ACCOUNT | ACCOUNTDISABLE
    assert _account_enabled("66050") is False  # DONT_EXPIRE_PASSWORD | ACCOUNTDISABLE | NORMAL_ACCOUNT
    # Unreadable: never a false « disabled »
    assert _account_enabled(None) is True
    assert _account_enabled("junk") is True
