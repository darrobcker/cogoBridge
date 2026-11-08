"""Passkeys for the web client (PROTOCOL.md §5): the WebAuthn ceremonies, checked by py_webauthn and answered from
`net`, where the rules are, as `oauth.py` does for an app's sign-in.

User verification is required both ways, the relying party is this server's own host, and each challenge is for one
use, one purpose and, when adding, one person. A passkey's PRF extension gives a secret only the authenticator can
derive: the browser sends it with the ceremony, `net` locks or opens the person's key under it, and nothing keeps it.
One salt for everyone, since a sign-in names no account before the passkey answers, and each passkey derives its own.
"""
from __future__ import annotations

import hashlib
import json
from urllib.parse import urlparse

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, parse_client_data_json
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from . import net, vault

PRF_SALT = vault.encode(hashlib.sha256(b"bridge passkey prf v1").digest())
UNCHECKED = "that passkey did not check out: try again"


class Passkeys:
    def __init__(self, store, base_url: str):
        parsed = urlparse(base_url)
        self.store, self.rp_id, self.origin = store, parsed.hostname or "", f"{parsed.scheme}://{parsed.netloc}"

    def _options(self, made) -> dict:
        options = json.loads(options_to_json(made))
        options["extensions"] = {"prf": {"eval": {"first": PRF_SALT}}}
        return options

    @staticmethod
    def _challenge(credential) -> str:
        try:
            data = base64url_to_bytes(credential["response"]["clientDataJSON"])
            return vault.encode(parse_client_data_json(data).challenge)
        except (KeyError, TypeError, ValueError, WebAuthnException):
            raise net.Refused(UNCHECKED) from None

    @staticmethod
    def _prf(given) -> bytes | None:
        if not given:
            return None
        try:
            prf = base64url_to_bytes(given) if isinstance(given, str) else b""
        except ValueError:
            prf = b""
        if len(prf) != 32:
            raise net.Refused(UNCHECKED)
        return prf

    def options_to_add(self, person: str) -> dict:
        handle = net.passkey_handle(self.store, person)
        challenge = net.passkey_challenge(self.store, "add", person, handle=handle)
        return self._options(generate_registration_options(
            rp_id=self.rp_id, rp_name="Bridge", user_name="Bridge", user_display_name="Bridge",
            user_id=vault.decode(handle), challenge=vault.decode(challenge),
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.REQUIRED),
            exclude_credentials=[PublicKeyCredentialDescriptor(id=vault.decode(c))
                                 for c in net.passkey_ids(self.store, person)]))

    def add(self, person: str, credential, prf, session: str) -> bool:
        """Returns whether the new passkey opens their key (it gave a PRF secret)."""
        kept = net.take_passkey_challenge(self.store, self._challenge(credential), "add", person)
        if kept is None:
            raise net.Refused("that took too long: try again")
        try:
            verified = verify_registration_response(
                credential=credential, expected_challenge=vault.decode(self._challenge(credential)),
                expected_rp_id=self.rp_id, expected_origin=self.origin, require_user_verification=True)
        except (WebAuthnException, KeyError, TypeError, ValueError):
            raise net.Refused(UNCHECKED) from None
        return net.add_passkey(self.store, person, vault.encode(verified.credential_id),
                               verified.credential_public_key, verified.sign_count, kept["handle"], self._prf(prf),
                               session=session)

    def options_to_use(self, person: str = "", credential_id: str = "") -> dict:
        """To sign in with any passkey for this server; or, with `person` and `credential_id`, to use that one passkey
        of theirs once more for the PRF secret it did not give when it was made."""
        challenge = net.passkey_challenge(self.store, "key" if person else "sign-in", person)
        allow = [PublicKeyCredentialDescriptor(id=vault.decode(credential_id))] if person else None
        return self._options(generate_authentication_options(
            rp_id=self.rp_id, challenge=vault.decode(challenge), allow_credentials=allow,
            user_verification=UserVerificationRequirement.REQUIRED))

    def _verified(self, credential, purpose: str, person: str = ""):
        if net.take_passkey_challenge(self.store, self._challenge(credential), purpose, person) is None:
            raise net.Refused("that took too long: try again")
        try:
            raw = credential["rawId"]
            credential_id = vault.encode(base64url_to_bytes(raw))
        except (KeyError, TypeError, ValueError):
            raise net.Refused(UNCHECKED) from None
        stored = net.passkey(self.store, credential_id)
        if not stored or (person and stored["person_id"] != person):
            raise net.NotYours()
        try:
            verified = verify_authentication_response(
                credential=credential, expected_challenge=vault.decode(self._challenge(credential)),
                expected_rp_id=self.rp_id, expected_origin=self.origin, credential_public_key=stored["public_key"],
                credential_current_sign_count=stored["sign_count"], require_user_verification=True)
        except (WebAuthnException, KeyError, TypeError, ValueError):
            raise net.Refused(UNCHECKED) from None
        return credential_id, verified.new_sign_count, stored["sign_count"]

    def sign_in(self, credential, prf) -> str:
        credential_id, count, was = self._verified(credential, "sign-in")
        return net.passkey_sign_in(self.store, credential_id, count, self._prf(prf), was=was)

    def key(self, person: str, credential, prf, session: str) -> None:
        prf = self._prf(prf)
        if prf is None:
            raise net.Refused(net.NO_PRF)
        credential_id, count, _ = self._verified(credential, "key", person)
        net.key_passkey(self.store, person, credential_id, count, prf, session=session)
