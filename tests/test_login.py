from tradedesk.upstox import is_auth_failure, login_problem

INVALID_CODE = ("HTTP 401: [{'errorCode': 'UDAPI100057', 'message': 'Invalid Auth code', 'propertyPath': None, "
                "'invalidValue': None, 'error_code': 'UDAPI100057'}]")


def test_used_or_expired_code_says_log_in_again():
    msg = login_problem(INVALID_CODE)
    assert "expired or was already used" in msg
    assert "Login with Upstox" in msg


def test_redirect_mismatch():
    assert "Redirect URL" in login_problem("HTTP 400: [{'message': 'Check your redirect_uri'}]")


def test_bad_key():
    assert "API key or secret" in login_problem("HTTP 401: [{'errorCode': 'UDAPI100016', 'message': 'Invalid Credentials'}]")


def test_unknown_error_still_plain():
    assert "try again" in login_problem("HTTP 500: boom")


def test_auth_failure_detection():
    assert is_auth_failure("holdings: HTTP 401: [{'errorCode': 'UDAPI100050', 'message': 'Invalid token used'}]")
    assert not is_auth_failure("holdings: HTTP 500: timeout")
