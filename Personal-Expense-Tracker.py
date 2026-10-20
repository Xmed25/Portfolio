import sqlite3
from pathlib import Path
from datetime import date
from decimal import Decimal, InvalidOperation

DB_PATH = Path(__file__).parent / "expenses.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                currency TEXT NOT NULL DEFAULT 'EGP',
                opening_balance INTEGER NOT NULL DEFAULT 0
                    CHECK(opening_balance >= 0)
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL
                    CHECK(type IN ('income','expense','both'))
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                category_id INTEGER,
                type TEXT NOT NULL
                    CHECK(type IN ('income','expense')),
                amount INTEGER NOT NULL CHECK(amount > 0),
                currency TEXT NOT NULL,
                date TEXT NOT NULL,
                note TEXT DEFAULT '',
                FOREIGN KEY(account_id) REFERENCES accounts(id),
                FOREIGN KEY(category_id) REFERENCES categories(id)
                    ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER,
                month TEXT NOT NULL,
                amount INTEGER NOT NULL CHECK(amount > 0),
                currency TEXT NOT NULL,
                UNIQUE(category_id, month, currency),
                FOREIGN KEY(category_id) REFERENCES categories(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL REFERENCES accounts(id),
                destination_id INTEGER NOT NULL REFERENCES accounts(id),
                amount INTEGER NOT NULL CHECK(amount > 0),
                currency TEXT NOT NULL,
                date TEXT NOT NULL,
                CHECK(source_id != destination_id)
            );

            CREATE TABLE IF NOT EXISTS debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person TEXT NOT NULL,
                direction TEXT NOT NULL
                    CHECK(direction IN ('owed_to_me','i_owe')),
                amount INTEGER NOT NULL CHECK(amount > 0),
                paid INTEGER NOT NULL DEFAULT 0
                    CHECK(paid >= 0 AND paid <= amount),
                currency TEXT NOT NULL DEFAULT 'EGP'
            );

            CREATE TABLE IF NOT EXISTS savings_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                target INTEGER NOT NULL CHECK(target > 0),
                saved INTEGER NOT NULL DEFAULT 0
                    CHECK(saved >= 0 AND saved <= target),
                currency TEXT NOT NULL DEFAULT 'EGP'
            );
        """)

        conn.executemany("""
            INSERT OR IGNORE INTO categories(name, type)
            VALUES (?, ?)
        """, [
            ("Salary", "income"),
            ("Freelance", "income"),
            ("Other income", "income"),
            ("Food", "expense"),
            ("Transport", "expense"),
            ("Bills", "expense"),
            ("Shopping", "expense"),
            ("Health", "expense"),
            ("Education", "expense"),
            ("Entertainment", "expense"),
            ("Other", "both")
        ])



def to_minor_units(value):
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid amount.")

    if not amount.is_finite() or amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    if amount.as_tuple().exponent < -2:
        raise ValueError("Use at most two decimal places.")

    return int(amount * 100)


def money(amount, currency="EGP"):
    return f"{amount / 100:,.2f} {currency}"


def ask_amount(prompt="Amount: "):
    while True:
        try:
            return to_minor_units(input(prompt))
        except ValueError as error:
            print(error)


def ask_date():
    value = input(f"Date YYYY-MM-DD [{date.today()}]: ").strip()
    value = value or date.today().isoformat()

    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError("Date must be YYYY-MM-DD.")


def ask_month():
    value = input(f"Month YYYY-MM [{date.today():%Y-%m}]: ").strip()
    value = value or date.today().strftime("%Y-%m")

    try:
        date.fromisoformat(value + "-01")
        return value
    except ValueError:
        raise ValueError("Month must be YYYY-MM.")




def create_account():
    name = input("Account name: ").strip()
    if not name:
        print("Account name cannot be empty.")
        return

    print("1. Cash  2. Bank  3. E-wallet  4. Other")
    account_type = {
        "1": "cash", "2": "bank", "3": "ewallet", "4": "other"
    }.get(input("Account type: ").strip())

    if account_type is None:
        print("Invalid account type.")
        return

    currency = input("Currency [EGP]: ").strip().upper() or "EGP"
    if len(currency) != 3 or not currency.isalpha():
        print("Currency must be a 3-letter code.")
        return

    opening = input("Opening balance (0 if empty): ").strip() or "0"

    try:
        opening_balance = int(to_minor_units(opening)) if Decimal(opening) > 0 else 0
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO accounts(name, currency, opening_balance)
                VALUES (?, ?, ?)
            """, (name, currency, opening_balance))
        print("Account created successfully.")
    except (ValueError, InvalidOperation, sqlite3.IntegrityError) as error:
        print("Could not create account:", error)


def get_balance(account_id):
    with get_connection() as conn:
        account = conn.execute(
            "SELECT * FROM accounts WHERE id=?", (account_id,)
        ).fetchone()

        if not account:
            raise ValueError("Account not found.")

        net = conn.execute("""
            SELECT COALESCE(SUM(
                CASE WHEN type='income' THEN amount ELSE -amount END
            ), 0)
            FROM transactions WHERE account_id=?
        """, (account_id,)).fetchone()[0]

        incoming = conn.execute("""
            SELECT COALESCE(SUM(amount),0) FROM transfers
            WHERE destination_id=?
        """, (account_id,)).fetchone()[0]

        outgoing = conn.execute("""
            SELECT COALESCE(SUM(amount),0) FROM transfers
            WHERE source_id=?
        """, (account_id,)).fetchone()[0]

        return account["opening_balance"] + net + incoming - outgoing


def list_accounts():
    with get_connection() as conn:
        return conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()


def show_accounts():
    accounts = list_accounts()
    if not accounts:
        print("No accounts. Create one first.")
        return

    for account in accounts:
        print(
            f'{account["id"]}. {account["name"]} '
            f'({account["currency"]}) — '
            f'{money(get_balance(account["id"]), account["currency"])}'
        )


def choose_account():
    show_accounts()
    try:
        account_id = int(input("Account ID: "))
        with get_connection() as conn:
            account = conn.execute(
                "SELECT * FROM accounts WHERE id=?", (account_id,)
            ).fetchone()
        if account:
            return account
    except ValueError:
        pass

    print("Invalid account.")
    return None




def list_categories(kind=None):
    with get_connection() as conn:
        if kind:
            return conn.execute("""
                SELECT * FROM categories
                WHERE type IN (?, 'both')
                ORDER BY name
            """, (kind,)).fetchall()

        return conn.execute(
            "SELECT * FROM categories ORDER BY name"
        ).fetchall()


def choose_category(kind):
    categories = list_categories(kind)
    for category in categories:
        print(f'{category["id"]}. {category["name"]}')

    raw = input("Category ID (blank for none): ").strip()
    if not raw:
        return None

    try:
        category_id = int(raw)
        if any(c["id"] == category_id for c in categories):
            return category_id
    except ValueError:
        pass

    print("Invalid category.")
    return None


def create_category():
    name = input("Category name: ").strip()
    kind = input("Type (income/expense/both): ").strip().lower()

    if not name or kind not in ("income", "expense", "both"):
        print("Invalid category information.")
        return

    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO categories(name, type) VALUES (?, ?)",
                (name, kind)
            )
        print("Category created.")
    except sqlite3.IntegrityError:
        print("That category already exists.")




def add_transaction(kind):
    account = choose_account()
    if account is None:
        return

    print("\nCategories:")
    category_id = choose_category(kind)
    amount = ask_amount()
    transaction_date = ask_date()
    note = input("Note (optional): ").strip()

    with get_connection() as conn:
        if category_id is not None:
            category = conn.execute(
                "SELECT type FROM categories WHERE id=?", (category_id,)
            ).fetchone()

            if not category or category["type"] not in (kind, "both"):
                print("Category type does not match.")
                return

        conn.execute("""
            INSERT INTO transactions(
                account_id, category_id, type, amount,
                currency, date, note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            account["id"], category_id, kind, amount,
            account["currency"], transaction_date, note
        ))

    print("Transaction saved.")


def list_transactions():
    with get_connection() as conn:
        return conn.execute("""
            SELECT t.*, a.name AS account_name,
                   c.name AS category_name
            FROM transactions t
            JOIN accounts a ON a.id=t.account_id
            LEFT JOIN categories c ON c.id=t.category_id
            ORDER BY t.date DESC, t.id DESC
        """).fetchall()


def show_transactions():
    rows = list_transactions()
    if not rows:
        print("No transactions.")
        return

    for t in rows:
        sign = "+" if t["type"] == "income" else "-"
        print(
            f'#{t["id"]} | {t["date"]} | {t["type"]} | '
            f'{sign}{money(t["amount"], t["currency"])} | '
            f'{t["account_name"]} | {t["category_name"] or "Uncategorized"} '
            f'| {t["note"]}'
        )


def delete_transaction():
    show_transactions()
    try:
        transaction_id = int(input("Transaction ID to delete: "))
    except ValueError:
        print("Invalid ID.")
        return

    if input("Confirm deletion? (y/n): ").strip().lower() != "y":
        print("Cancelled.")
        return

    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM transactions WHERE id=?", (transaction_id,)
        )

    print("Deleted." if cursor.rowcount else "Transaction not found.")




def set_budget():
    month = ask_month()
    print("1. Overall budget  2. Category budget")
    choice = input("Choose: ").strip()

    category_id = None
    if choice == "2":
        category_id = choose_category("expense")
        if category_id is None:
            print("Choose a valid category.")
            return
    elif choice != "1":
        print("Invalid choice.")
        return

    currency = input("Currency [EGP]: ").strip().upper() or "EGP"
    amount = ask_amount()

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO budgets(category_id, month, amount, currency)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(category_id, month, currency)
            DO UPDATE SET amount=excluded.amount
        """, (category_id, month, amount, currency))

    print("Budget saved.")


def show_budget_status():
    month = ask_month()

    with get_connection() as conn:
        budgets = conn.execute("""
            SELECT b.*, c.name AS category_name
            FROM budgets b
            LEFT JOIN categories c ON c.id=b.category_id
            WHERE b.month=?
        """, (month,)).fetchall()

        for budget in budgets:
            if budget["category_id"] is None:
                spent = conn.execute("""
                    SELECT COALESCE(SUM(amount),0)
                    FROM transactions
                    WHERE type='expense' AND currency=?
                      AND substr(date,1,7)=?
                """, (budget["currency"], month)).fetchone()[0]
                label = "Overall budget"
            else:
                spent = conn.execute("""
                    SELECT COALESCE(SUM(amount),0)
                    FROM transactions
                    WHERE type='expense' AND category_id=?
                      AND currency=? AND substr(date,1,7)=?
                """, (
                    budget["category_id"], budget["currency"], month
                )).fetchone()[0]
                label = budget["category_name"]

            remaining = budget["amount"] - spent
            print(
                f'{label}: budget {money(budget["amount"], budget["currency"])} | '
                f'spent {money(spent, budget["currency"])} | '
                f'remaining {money(remaining, budget["currency"])}'
            )

            if spent > budget["amount"]:
                print("WARNING: Budget exceeded!")
            elif spent == budget["amount"]:
                print("Budget limit reached.")

        if not budgets:
            print("No budgets set for this month.")



def monthly_report():
    month = ask_month()

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT currency,
                SUM(CASE WHEN type='income' THEN amount ELSE 0 END) AS income,
                SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) AS expenses
            FROM transactions
            WHERE substr(date,1,7)=?
            GROUP BY currency
        """, (month,)).fetchall()

        for row in rows:
            income = row["income"] or 0
            expenses = row["expenses"] or 0
            currency = row["currency"]

            print(f"\nReport for {month} ({currency})")
            print("Income:", money(income, currency))
            print("Expenses:", money(expenses, currency))
            print("Net:", money(income - expenses, currency))

        categories = conn.execute("""
            SELECT c.name, t.currency, SUM(t.amount) AS total
            FROM transactions t
            LEFT JOIN categories c ON c.id=t.category_id
            WHERE t.type='expense' AND substr(t.date,1,7)=?
            GROUP BY c.name, t.currency
            ORDER BY total DESC
        """, (month,)).fetchall()

        print("\nExpenses by category:")
        for c in categories:
            print(
                f'{c["name"] or "Uncategorized"}: '
                f'{money(c["total"], c["currency"])}'
            )

        if not rows:
            print("No transactions for this month.")




def transfer():
    print("Source account:")
    source = choose_account()
    if source is None:
        return

    print("Destination account:")
    destination = choose_account()
    if destination is None:
        return

    if source["id"] == destination["id"]:
        print("Choose two different accounts.")
        return

    if source["currency"] != destination["currency"]:
        print("Currencies must match; conversion is not supported.")
        return

    amount = ask_amount()
    transfer_date = ask_date()

    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")

        balance = get_balance(source["id"])
        if balance < amount:
            print("Insufficient funds.")
            return

        conn.execute("""
            INSERT INTO transfers(
                source_id, destination_id, amount, currency, date
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            source["id"], destination["id"], amount,
            source["currency"], transfer_date
        ))

    print("Transfer completed.")




def add_debt():
    person = input("Person or organization: ").strip()
    if not person:
        print("Name is required.")
        return

    print("1. Money owed to me  2. Money I owe")
    direction = {"1": "owed_to_me", "2": "i_owe"}.get(
        input("Choose: ").strip()
    )

    if not direction:
        print("Invalid choice.")
        return

    amount = ask_amount()
    currency = input("Currency [EGP]: ").strip().upper() or "EGP"

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO debts(person, direction, amount, currency)
            VALUES (?, ?, ?, ?)
        """, (person, direction, amount, currency))

    print("Debt recorded.")


def show_debts():
    with get_connection() as conn:
        debts = conn.execute("SELECT * FROM debts ORDER BY id").fetchall()

    if not debts:
        print("No debts recorded.")

    for d in debts:
        print(
            f'#{d["id"]} {d["person"]} | {d["direction"]} | '
            f'original {money(d["amount"], d["currency"])} | '
            f'paid {money(d["paid"], d["currency"])} | '
            f'remaining {money(d["amount"]-d["paid"], d["currency"])}'
        )


def pay_debt():
    show_debts()
    try:
        debt_id = int(input("Debt ID: "))
    except ValueError:
        print("Invalid ID.")
        return

    amount = ask_amount()

    with get_connection() as conn:
        debt = conn.execute(
            "SELECT * FROM debts WHERE id=?", (debt_id,)
        ).fetchone()

        if not debt:
            print("Debt not found.")
            return

        if debt["paid"] + amount > debt["amount"]:
            print("Payment exceeds remaining debt.")
            return

        conn.execute(
            "UPDATE debts SET paid=paid+? WHERE id=?",
            (amount, debt_id)
        )

    print("Payment recorded.")



def savings_menu():
    print("1. Create goal  2. Add savings  3. View goals")
    choice = input("Choose: ").strip()

    if choice == "1":
        name = input("Goal name: ").strip()
        target = ask_amount()
        currency = input("Currency [EGP]: ").strip().upper() or "EGP"

        with get_connection() as conn:
            conn.execute("""
                INSERT INTO savings_goals(name, target, currency)
                VALUES (?, ?, ?)
            """, (name, target, currency))

        print("Savings goal created.")

    elif choice == "2":
        show_savings_goals()
        try:
            goal_id = int(input("Goal ID: "))
        except ValueError:
            print("Invalid ID.")
            return

        amount = ask_amount()

        with get_connection() as conn:
            goal = conn.execute(
                "SELECT * FROM savings_goals WHERE id=?", (goal_id,)
            ).fetchone()

            if not goal:
                print("Goal not found.")
                return

            if goal["saved"] + amount > goal["target"]:
                print("Contribution exceeds target.")
                return

            conn.execute(
                "UPDATE savings_goals SET saved=saved+? WHERE id=?",
                (amount, goal_id)
            )

        print("Savings updated.")

    elif choice == "3":
        show_savings_goals()

    else:
        print("Invalid choice.")


def show_savings_goals():
    with get_connection() as conn:
        goals = conn.execute(
            "SELECT * FROM savings_goals ORDER BY id"
        ).fetchall()

    if not goals:
        print("No savings goals.")

    for goal in goals:
        percent = goal["saved"] / goal["target"] * 100
        print(
            f'#{goal["id"]} {goal["name"]} | '
            f'{money(goal["saved"], goal["currency"])} / '
            f'{money(goal["target"], goal["currency"])} | {percent:.1f}%'
        )


def main():
    initialize_database()

    while True:
        print("""
========================================
       PERSONAL EXPENSE TRACKER
========================================
1.  Create account
2.  View accounts and balances
3.  Add income
4.  Add expense
5.  View transactions
6.  Delete transaction
7.  Add category
8.  Set budget
9.  View budget status
10. Monthly report
11. Transfer between accounts
12. Add debt
13. View debts
14. Record debt payment
15. Savings goals
0.  Exit
========================================
""")

        choice = input("Choose an option: ").strip()

        actions = {
            "1": create_account,
            "2": show_accounts,
            "3": lambda: add_transaction("income"),
            "4": lambda: add_transaction("expense"),
            "5": show_transactions,
            "6": delete_transaction,
            "7": create_category,
            "8": set_budget,
            "9": show_budget_status,
            "10": monthly_report,
            "11": transfer,
            "12": add_debt,
            "13": show_debts,
            "14": pay_debt,
            "15": savings_menu
        }

        if choice == "0":
            print("Your data has been saved. Goodbye!")
            break

        action = actions.get(choice)
        if action:
            try:
                action()
            except (ValueError, sqlite3.Error) as error:
                print("Operation failed:", error)
        else:
            print("Invalid choice.")

        input("\nPress Enter to continue...")


if __name__ == "__main__":
    main()
