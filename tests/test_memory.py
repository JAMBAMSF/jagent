import time
from agent.memory import upsert_user, upsert_counterparty, list_counterparties, rename_counterparty, set_risk_tolerance, forget_user

def test_user_and_risk(conn):
    uid = upsert_user(conn, "Test User", "moderate")
    set_risk_tolerance(conn, uid, "aggressive")
    forget_user(conn, "Test User")

def test_rename_promote_global(conn):
    cur = conn.cursor()
    now = time.time()
    cur.execute(
        "INSERT INTO counterparties(user_id, counterparty, first_seen, last_seen, times_used) VALUES (NULL, ?, ?, ?, 0)",
        ("ConEd", now, now),
    )
    conn.commit()

    uid = upsert_user(conn, "U", "moderate")

    result = rename_counterparty(conn, uid, "ConEd", "Con Edison Premier Services")
    assert result in {"renamed", "merged"}

    names = list_counterparties(conn, uid)
    assert "Con Edison Premier Services" in names
    assert "ConEd" not in names

def test_rename_merge_when_target_exists(conn):
    uid = upsert_user(conn, "U2", "moderate")
    upsert_counterparty(conn, uid, "American Express Centurion")
    upsert_counterparty(conn, uid, "AMERICAN EXPRESS")  
    result = rename_counterparty(conn, uid, "AMERICAN EXPRESS", "American Express Centurion")
    assert result == "merged"

def test_list_counterparties_includes_user_and_globals(conn):
    uid = upsert_user(conn, "U3", "moderate")
    cur = conn.cursor()
    now = time.time()
    cur.execute(
        "INSERT INTO counterparties(user_id, counterparty, first_seen, last_seen, times_used) VALUES (NULL, ?, ?, ?, 0)",
        ("Verizon", now, now),
    )
    conn.commit()
    upsert_counterparty(conn, uid, "U.S. Treasury - I.R.S.")
    names = list_counterparties(conn, uid)
    assert any("Verizon" == n for n in names)
    assert any("U.S. Treasury - I.R.S." == n for n in names)
