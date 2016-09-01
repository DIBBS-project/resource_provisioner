from models import Profile
from Crypto.PublicKey import RSA
from base64 import b64decode, b64encode
import json


def decrypt_credentials(encrypted_credentials, user_id):
    # Use the private key de temporarily decrypt and check that it gives JSON
    profile = Profile.objects.get(user_id=user_id)
    key = RSA.importKey(profile.rsa_key)

    to_decrypt = b64decode(encrypted_credentials)
    decrypted_credentials = key.decrypt(to_decrypt)

    # Temporary fix
    # TODO: Understand why there are additional characters at the beginning and fix this hack
    import string
    pos = string.rfind(decrypted_credentials, '{')
    print(pos)
    decrypted_credentials = decrypted_credentials[string.rfind(decrypted_credentials, '{'):]
    decrypted_credentials = json.loads(decrypted_credentials)
    return decrypted_credentials
