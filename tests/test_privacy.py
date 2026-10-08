import base64
import secrets
import unittest

from privacy import PrivacyCipher, decode_data_key, mask_value, validate_kind


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.encoded_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
        self.cipher = PrivacyCipher(self.encoded_key)

    def test_key_requires_32_bytes(self):
        self.assertEqual(32, len(decode_data_key(self.encoded_key)))
        with self.assertRaises(ValueError):
            decode_data_key(base64.urlsafe_b64encode(b"short").decode("ascii"))

    def test_mask_reservation(self):
        self.assertEqual("********1234", mask_value("reservation", "ABCD56781234"))

    def test_mask_phone_preserves_separators_and_last_four_digits(self):
        self.assertEqual("***-****-5678", mask_value("phone", "010-1234-5678"))

    def test_mask_email(self):
        self.assertEqual("k***@e***.com", mask_value("email", "kwonn@example.com"))

    def test_encrypt_decrypt_round_trip_and_aad_binding(self):
        nonce, ciphertext = self.cipher.encrypt(
            "record-1", "reservation", "SRT 예매번호", "ABCDEF123456"
        )
        payload = self.cipher.decrypt("record-1", "reservation", nonce, ciphertext)
        self.assertEqual("SRT 예매번호", payload["label"])
        self.assertEqual("ABCDEF123456", payload["value"])

        with self.assertRaises(Exception):
            self.cipher.decrypt("record-2", "reservation", nonce, ciphertext)

    def test_validate_kind(self):
        self.assertEqual("phone", validate_kind(" PHONE "))
        with self.assertRaises(ValueError):
            validate_kind("password")


if __name__ == "__main__":
    unittest.main()
