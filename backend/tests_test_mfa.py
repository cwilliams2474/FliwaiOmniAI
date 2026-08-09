from app.mfa import generate_secret, provisioning_uri, totp, verify_totp

def test_totp_round_trip_at_fixed_time():
    secret = generate_secret(); now = 1786230000
    code = totp(secret, now)
    assert len(code) == 6 and code.isdigit()
    assert verify_totp(secret, code, now)
    assert not verify_totp(secret, '000000' if code != '000000' else '111111', now)

def test_provisioning_uri_is_otpauth():
    uri = provisioning_uri('JBSWY3DPEHPK3PXP', 'person@example.com')
    assert uri.startswith('otpauth://totp/') and 'secret=JBSWY3DPEHPK3PXP' in uri
