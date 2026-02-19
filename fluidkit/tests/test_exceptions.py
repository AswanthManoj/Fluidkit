from fluidkit.exceptions import HTTPError, Redirect, error

def test_exceptions():

    # Test 1: Can create exceptions
    err = HTTPError(404, "Not found")
    print(err.status, err.message)

    # Test 2: Validation works
    try:
        HTTPError(200, "OK")  # Should fail - not an error code
    except ValueError as e:
        print("✅ Validation caught:", e)

    # Test 3: error() helper raises
    try:
        error(404, "User not found")
    except HTTPError as e:
        print("✅ Caught:", e.status, e.message)
