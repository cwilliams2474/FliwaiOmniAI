from typing import Protocol


class TokenUser(Protocol):
    email: str
    token_version: int


def token_identity(user: TokenUser) -> dict[str, object]:
    return {'sub': user.email, 'ver': int(user.token_version)}
