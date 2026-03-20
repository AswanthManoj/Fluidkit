import httpx

BASE = "http://localhost:8000/remote/src/lib/test"

tests = [
    ("int param - valid", "/get_number", {"n": 5}, 200),
    ("int param - string coerce", "/get_number", {"n": "3"}, 200),
    ("int param - invalid string", "/get_number", {"n": "hello"}, 400),
    ("int param - float coerce", "/get_number", {"n": 3.0}, 200),
    ("int param - bool coerce", "/get_number", {"n": True}, 200),
    ("int param - null", "/get_number", {"n": None}, 400),
    ("int param - list", "/get_number", {"n": [1, 2]}, 400),

    ("str param - valid", "/get_greeting", {"name": "Alice", "loud": False}, 200),
    ("str param - int rejected", "/get_greeting", {"name": 123, "loud": False}, 400),
    ("bool param - string coerce", "/get_greeting", {"name": "Alice", "loud": "yes"}, 200),
    ("bool param - int coerce", "/get_greeting", {"name": "Alice", "loud": 1}, 200),

    ("pydantic - valid", "/create_user", {"user": {"name": "Bob", "age": 25}}, 200),
    ("pydantic - missing field", "/create_user", {"user": {"name": "Bob"}}, 400),
    ("pydantic - wrong type", "/create_user", {"user": {"name": "Bob", "age": "old"}}, 400),
    ("pydantic - extra field", "/create_user", {"user": {"name": "Bob", "age": 25, "email": "a@b.com"}}, 200),

    ("optional return - valid", "/find_user", {"user_id": "1"}, 200),
    ("optional return - wrong type", "/find_user", {"user_id": 123}, 400),

    ("missing param", "/get_number", {}, 400),
    ("extra param ignored", "/get_number", {"n": 5, "extra": "junk"}, 200),
]

def run():
    with httpx.Client() as client:
        passed = 0
        failed = 0

        for label, path, payload, expect in tests:
            try:
                r = client.post(f"{BASE}{path}", json=payload)
                status = r.status_code
                icon = "PASS" if status == expect else "FAIL"

                if status != expect:
                    failed += 1
                    body = r.json()
                    print(f"  [{icon}] {label}")
                    print(f"         expected {expect}, got {status}")
                    print(f"         response: {body.get('message', body)}")
                else:
                    passed += 1
                    print(f"  [{icon}] {label}")

            except Exception as e:
                failed += 1
                print(f"  [ERR]  {label}")
                print(f"         {e}")

        print(f"\n  {passed} passed, {failed} failed, {passed + failed} total")

if __name__ == "__main__":
    run()
